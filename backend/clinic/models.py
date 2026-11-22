from django.conf import settings
from django.db import models
from django.db.models import BigIntegerField, Case, F, Q, Value, When


class Specialty(models.Model):
    name = models.CharField(max_length=80, unique=True)

    class Meta:
        verbose_name_plural = "specialties"

    def __str__(self):
        return self.name


class Doctor(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    specialty = models.ForeignKey(Specialty, on_delete=models.PROTECT)

    def __str__(self):
        return f"Dr. {self.user.get_full_name() or self.user.username}"


class Patient(models.Model):
    name = models.CharField(max_length=120)
    date_of_birth = models.DateField(null=True, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Appointment(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled"
        COMPLETED = "completed"
        CANCELLED = "cancelled"
        NO_SHOW = "no_show"

    doctor = models.ForeignKey(Doctor, on_delete=models.PROTECT, related_name="appointments")
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name="appointments")
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.SCHEDULED)
    reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(end_at__gt=F("start_at")), name="appt_end_after_start"),
        ]
        indexes = [
            models.Index(fields=["doctor", "start_at"], name="appt_doctor_start_idx"),
            # Date-range queries across all doctors (dashboard, day list). Leads with start_at so MySQL
            # can range-scan; includes doctor + status so aggregates are answered from the index alone.
            models.Index(fields=["start_at", "doctor", "status"], name="appt_start_doctor_status_idx"),
            models.Index(fields=["status", "start_at"], name="appt_status_start_idx"),
        ]


class AppointmentSlot(models.Model):
    """One row per grid slot an appointment occupies.

    MySQL has no exclusion constraints, so overlap prevention is expressed as plain
    uniqueness: two live appointments can't claim the same (doctor, slot_start).
    Cancelling an appointment deletes its slot rows, which frees the time.
    """
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name="slots")
    doctor = models.ForeignKey(Doctor, on_delete=models.PROTECT)
    slot_start = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["doctor", "slot_start"], name="uniq_doctor_slot"),
        ]
        # The unique key above leads with doctor; utilization asks "slots in a date range, all doctors".
        indexes = [models.Index(fields=["slot_start", "doctor"], name="slot_start_doctor_idx")]


class QueueEntry(models.Model):
    class Status(models.TextChoices):
        WAITING = "waiting"
        IN_CONSULTATION = "in_consultation"
        COMPLETED = "completed"
        NO_SHOW = "no_show"

    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE, related_name="queue_entry")
    doctor = models.ForeignKey(Doctor, on_delete=models.PROTECT, related_name="queue_entries")
    queue_date = models.DateField()  # clinic-local date
    token_number = models.PositiveIntegerField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.WAITING)
    checked_in_at = models.DateTimeField()
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    # MySQL has no partial unique indexes. Workaround: a stored generated column that is the
    # doctor id while in consultation and NULL otherwise, with a UNIQUE index on it.
    # MySQL allows many NULLs in a unique index, so only one "in_consultation" row can exist.
    in_consult_key = models.GeneratedField(
        expression=Case(When(Q(status="in_consultation"), then=F("doctor_id")),
                        default=Value(None), output_field=BigIntegerField(null=True)),
        output_field=BigIntegerField(null=True), db_persist=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["doctor", "queue_date", "token_number"],
                                    name="unique_token_per_doctor_day"),
            models.UniqueConstraint(fields=["in_consult_key"], name="one_in_consultation_per_doctor"),
        ]
        indexes = [models.Index(fields=["doctor", "queue_date", "status"], name="queue_doc_date_status_idx")]
        ordering = ["token_number"]
