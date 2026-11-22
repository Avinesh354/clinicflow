"""Demo-schedule generation, shared by `refresh_today` and the optional DEMO_MODE auto-refresh."""
import random
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Max

from .models import Appointment, AppointmentSlot, Doctor, Patient


def create_day_schedule(day, n_doctors=6):
    """Give the first `n_doctors` a schedule on `day`; doctors who already have one are skipped.

    Returns (added, skipped). Raises ValueError when there are no doctors or patients to use.
    """
    tz, step = ZoneInfo(settings.TIME_ZONE), settings.CLINIC_SLOT_MINUTES
    doctors = list(Doctor.objects.order_by("id")[:n_doctors])
    pids = list(Patient.objects.values_list("pk", flat=True)[:5000])
    if not doctors or not pids:
        raise ValueError("No doctors or patients yet. Run `python manage.py seed` first.")

    rnd = random.Random(day.toordinal())
    lo = datetime.combine(day, time(0, 0), tz)
    next_id = (Appointment.objects.aggregate(m=Max("id"))["m"] or 0) + 1
    appts, slots, skipped = [], [], 0
    for d in doctors:
        if Appointment.objects.filter(doctor=d, start_at__gte=lo, start_at__lt=lo + timedelta(days=1)).exists():
            skipped += 1  # already scheduled; never double up
            continue
        for k in range((8 * 60) // step):  # 09:00-17:00
            if rnd.random() < 0.4:
                continue
            start = datetime.combine(day, time(9, 0), tz) + timedelta(minutes=step * k)
            aid = next_id + len(appts)
            appts.append(Appointment(id=aid, doctor=d, patient_id=rnd.choice(pids), start_at=start,
                                     end_at=start + timedelta(minutes=step)))
            slots.append(AppointmentSlot(appointment_id=aid, doctor=d, slot_start=start))
    try:
        with transaction.atomic():
            Appointment.objects.bulk_create(appts, batch_size=2000)
            AppointmentSlot.objects.bulk_create(slots, batch_size=2000)
    except IntegrityError:  # a concurrent request created the same schedule first; nothing lost
        return 0, skipped
    return len(appts), skipped
