"""Read-only analytics. All aggregation happens in MySQL (conditional COUNTs, GROUP BY)."""
import datetime as _dt
from datetime import datetime, time, timedelta

from django.conf import settings
from django.db.models import Count, DateTimeField, ExpressionWrapper, F, Q
from django.db.models.functions import ExtractHour, ExtractIsoWeekDay, TruncDate
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.response import Response
from rest_framework.views import APIView

from .permissions import ADMIN, HasRole
from .models import Appointment, AppointmentSlot, Doctor


def _local_time():
    """start_at shifted to clinic-local wall time by plain arithmetic.

    Django's CONVERT_TZ path needs MySQL's named-zone tables even for UTC, which a fresh
    install often lacks (the result is silently NULL). Adding a fixed offset needs none.
    Exact for zones without DST (e.g. India); elsewhere it uses today's offset.
    """
    return ExpressionWrapper(F("start_at") + timezone.localtime().utcoffset(), output_field=DateTimeField())


def _totals(qs):
    t = qs.aggregate(
        total=Count("id"),
        completed=Count("id", filter=Q(status="completed")),
        no_show=Count("id", filter=Q(status="no_show")),
        cancelled=Count("id", filter=Q(status="cancelled")),
        scheduled=Count("id", filter=Q(status="scheduled")))
    seen = t["completed"] + t["no_show"]
    t["no_show_rate"] = round(100 * t["no_show"] / seen, 1) if seen else 0
    t["cancel_rate"] = round(100 * t["cancelled"] / t["total"], 1) if t["total"] else 0
    return t


class Overview(APIView):
    permission_classes = [HasRole]
    roles = (ADMIN,)

    def get(self, request):
        end = parse_date(request.query_params.get("to", "")) or timezone.localdate()
        start = parse_date(request.query_params.get("from", "")) or end - timedelta(days=89)
        if start > end or (end - start).days > 365:
            return Response({"detail": "Choose a date range of at most one year."}, status=400)
        doctor = request.query_params.get("doctor")
        local, utc = _local_time(), _dt.timezone.utc  # utc => Django adds no further conversion

        def window(a, b):  # inclusive local days -> queryset and aware bounds
            lo = timezone.make_aware(datetime.combine(a, time.min))
            hi = timezone.make_aware(datetime.combine(b + timedelta(days=1), time.min))
            qs = Appointment.objects.filter(start_at__gte=lo, start_at__lt=hi)
            return (qs.filter(doctor_id=doctor) if doctor else qs), lo, hi

        qs, lo, hi = window(start, end)
        span = (end - start).days + 1
        cur = _totals(qs)
        prev = _totals(window(start - timedelta(days=span), start - timedelta(days=1))[0])

        daily = list(qs.annotate(day=TruncDate(local, tzinfo=utc)).values("day")
                     .annotate(total=Count("id"), no_show=Count("id", filter=Q(status="no_show")))
                     .order_by("day"))
        heat = (qs.exclude(status="cancelled")
                .annotate(dow=ExtractIsoWeekDay(local, tzinfo=utc), hour=ExtractHour(local, tzinfo=utc))
                .values("dow", "hour").annotate(n=Count("id")).order_by("dow", "hour"))

        # Utilisation = booked grid slots / capacity (weekdays x slots per 8-hour day).
        weekdays = sum((start + timedelta(i)).weekday() < 5 for i in range(span))
        capacity = max(1, (480 // settings.CLINIC_SLOT_MINUTES) * weekdays)
        slots = AppointmentSlot.objects.filter(slot_start__gte=lo, slot_start__lt=hi)
        if doctor:
            slots = slots.filter(doctor_id=doctor)
        booked = dict(slots.values_list("doctor_id").annotate(n=Count("id")))
        names = {d.pk: str(d) for d in Doctor.objects.select_related("user")}
        by_doctor = []
        for r in qs.values("doctor_id").annotate(
                total=Count("id"), completed=Count("id", filter=Q(status="completed")),
                no_show=Count("id", filter=Q(status="no_show"))).order_by("-total"):
            seen = r["completed"] + r["no_show"]
            by_doctor.append({
                "doctor": names.get(r["doctor_id"], "?"), "total": r["total"],
                "no_show_rate": round(100 * r["no_show"] / seen, 1) if seen else 0,
                "utilization": min(100, round(100 * booked.get(r["doctor_id"], 0) / capacity, 1))})
        n_doctors = 1 if doctor else max(1, len(names))
        utilization = min(100, round(100 * sum(booked.values()) / (capacity * n_doctors), 1))

        return Response({
            "range": {"from": start, "to": end, "days": span},
            "kpis": {"current": {**cur, "utilization": utilization}, "previous": prev},
            "daily": daily, "heatmap": list(heat), "doctors": by_doctor})
