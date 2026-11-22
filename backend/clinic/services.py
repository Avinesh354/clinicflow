"""Business logic. Views stay thin; every race-prone operation lives here."""
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import Avg, DurationField, ExpressionWrapper, F, Max
from django.utils import timezone

from .models import Appointment, AppointmentSlot, Doctor, QueueEntry

MYSQL_DUPLICATE_ENTRY = 1062
MYSQL_DEADLOCK = 1213


class ClinicError(Exception):
    pass


class SlotTaken(ClinicError):
    pass


class InvalidSlot(ClinicError, ValueError):
    pass


class QueueError(ClinicError):
    pass


def _is_duplicate(exc, key_name):
    return bool(exc.args) and exc.args[0] == MYSQL_DUPLICATE_ENTRY and key_name in str(exc.args[-1])


def slot_starts(start, end):
    """Validate grid alignment and return the start of every slot the booking occupies."""
    step = settings.CLINIC_SLOT_MINUTES
    if timezone.is_naive(start) or timezone.is_naive(end):
        raise InvalidSlot("start and end must be timezone-aware.")
    if end <= start:
        raise InvalidSlot("end must be after start.")
    local = timezone.localtime(start)
    if local.second or local.microsecond or (local.hour * 60 + local.minute) % step:
        raise InvalidSlot(f"start must be on a {step}-minute boundary (clinic local time).")
    minutes = (end - start).total_seconds() / 60
    if minutes % step or minutes > settings.CLINIC_MAX_APPOINTMENT_MINUTES:
        raise InvalidSlot(f"duration must be a multiple of {step} min, at most "
                          f"{settings.CLINIC_MAX_APPOINTMENT_MINUTES}.")
    return [start + timedelta(minutes=step * i) for i in range(int(minutes // step))]


def book_appointment(*, doctor, patient, start, end, reason=""):
    """Insert the appointment and its slot rows atomically.

    The UNIQUE(doctor, slot_start) index is the arbiter: a concurrent overlapping booking
    blocks on the index, then fails with a duplicate-key error, and the whole transaction
    (including the appointment row) rolls back. Slots are inserted in ascending order so
    two bookings contend in the same order; a deadlock is retried defensively.
    """
    starts = slot_starts(start, end)
    for attempt in range(3):
        try:
            with transaction.atomic():
                appt = Appointment.objects.create(doctor=doctor, patient=patient,
                                                  start_at=start, end_at=end, reason=reason)
                AppointmentSlot.objects.bulk_create(
                    [AppointmentSlot(appointment=appt, doctor=doctor, slot_start=s) for s in starts])
                return appt
        except IntegrityError as exc:
            if _is_duplicate(exc, "uniq_doctor_slot"):
                raise SlotTaken("That time overlaps an existing appointment.") from exc
            raise
        except OperationalError as exc:
            if exc.args and exc.args[0] == MYSQL_DEADLOCK and attempt < 2:
                continue
            raise


def cancel_appointment(appointment_id):
    """Cancel and free the slots (delete occupancy rows)."""
    with transaction.atomic():
        appt = Appointment.objects.select_for_update().get(pk=appointment_id)
        if appt.status != Appointment.Status.SCHEDULED:
            raise QueueError("Only scheduled appointments can be cancelled.")
        if QueueEntry.objects.filter(appointment=appt).exists():
            raise QueueError("Patient already checked in.")
        appt.status = Appointment.Status.CANCELLED
        appt.save(update_fields=["status"])
        appt.slots.all().delete()
        return appt


def check_in(appointment):
    """Assign the next token for the doctor/day. Serialised per doctor via a row lock."""
    if appointment.status != Appointment.Status.SCHEDULED:
        raise QueueError("Only scheduled appointments can check in.")
    now = timezone.now()
    queue_date = timezone.localtime(appointment.start_at).date()
    with transaction.atomic():
        Doctor.objects.select_for_update().get(pk=appointment.doctor_id)
        if QueueEntry.objects.filter(appointment=appointment).exists():
            raise QueueError("Already checked in.")
        last = (QueueEntry.objects.filter(doctor_id=appointment.doctor_id, queue_date=queue_date)
                .aggregate(m=Max("token_number"))["m"] or 0)
        return QueueEntry.objects.create(
            appointment=appointment, doctor_id=appointment.doctor_id, queue_date=queue_date,
            token_number=last + 1, checked_in_at=now)


def start_consultation(entry_id):
    """Call the patient in. The partial unique index rejects a second concurrent patient."""
    try:
        with transaction.atomic():
            entry = QueueEntry.objects.select_for_update().get(pk=entry_id)
            if entry.status != QueueEntry.Status.WAITING:
                raise QueueError("Patient is not waiting.")
            entry.status = QueueEntry.Status.IN_CONSULTATION
            entry.started_at = timezone.now()
            entry.save(update_fields=["status", "started_at"])
            return entry
    except IntegrityError as exc:
        raise QueueError("Doctor already has a patient in consultation.") from exc


def finish_consultation(entry_id, *, no_show=False):
    with transaction.atomic():
        entry = QueueEntry.objects.select_for_update().select_related("appointment").get(pk=entry_id)
        allowed = QueueEntry.Status.WAITING if no_show else QueueEntry.Status.IN_CONSULTATION
        if entry.status != allowed:
            raise QueueError(f"Cannot move from {entry.status}.")
        entry.status = QueueEntry.Status.NO_SHOW if no_show else QueueEntry.Status.COMPLETED
        entry.ended_at = timezone.now()
        entry.save(update_fields=["status", "ended_at"])
        entry.appointment.status = (Appointment.Status.NO_SHOW if no_show
                                    else Appointment.Status.COMPLETED)
        entry.appointment.save(update_fields=["status"])
        return entry


def avg_consult_minutes(doctor_id, default=10.0, sample=50):
    recent = list(QueueEntry.objects.filter(doctor_id=doctor_id, status="completed",
                                            started_at__isnull=False, ended_at__isnull=False)
                  .order_by("-ended_at").values_list("pk", flat=True)[:sample])
    agg = (QueueEntry.objects.filter(pk__in=recent)
           .annotate(d=ExpressionWrapper(F("ended_at") - F("started_at"), output_field=DurationField()))
           .aggregate(a=Avg("d"))["a"])
    return agg.total_seconds() / 60 if agg else default


def doctor_queue_snapshot(doctor_id, queue_date=None):
    queue_date = queue_date or timezone.localdate()
    entries = list(QueueEntry.objects.filter(doctor_id=doctor_id, queue_date=queue_date)
                   .select_related("appointment__patient"))
    serving = next((e for e in entries if e.status == "in_consultation"), None)
    waiting = [e for e in entries if e.status == "waiting"]
    row = lambda e: {"entry_id": e.pk, "token": e.token_number, "patient": e.appointment.patient.name,
                     "checked_in_at": e.checked_in_at, "started_at": e.started_at}
    return {
        "now_serving": serving.token_number if serving else None,
        "serving": row(serving) if serving else None,
        "waiting_count": len(waiting),
        "waiting": [row(e) for e in waiting],
        "completed_count": sum(e.status == "completed" for e in entries),
        "avg_consult_minutes": round(avg_consult_minutes(doctor_id), 1),
    }


def patient_position(entry):
    """Position = waiting patients with a lower token + 1; wait adds the one inside, if any."""
    base = QueueEntry.objects.filter(doctor_id=entry.doctor_id, queue_date=entry.queue_date)
    ahead = base.filter(status="waiting", token_number__lt=entry.token_number).count()
    inside = base.filter(status="in_consultation").exists()
    avg = avg_consult_minutes(entry.doctor_id)
    return {"token": entry.token_number, "ahead_of_you": ahead, "position": ahead + 1,
            "estimated_wait_minutes": round((ahead + (1 if inside else 0)) * avg),
            "estimate_basis": f"rolling average consultation {avg:.1f} min (estimate)"}
