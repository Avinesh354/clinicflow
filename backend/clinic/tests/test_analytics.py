from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from clinic.models import Appointment, Doctor, Patient, Specialty


class OverviewTests(TestCase):
    def test_counts_rates_heatmap_and_validation(self):
        User = get_user_model()
        doc = Doctor.objects.create(user=User.objects.create_user("d"), specialty=Specialty.objects.create(name="GP"))
        pat = Patient.objects.create(name="P")
        day = timezone.localdate() - timedelta(days=3)
        start = timezone.make_aware(datetime.combine(day, time(9, 0)))
        for i, st in enumerate(["completed", "completed", "no_show", "cancelled"]):
            s = start + timedelta(minutes=20 * i)
            Appointment.objects.create(doctor=doc, patient=pat, start_at=s, end_at=s + timedelta(minutes=20), status=st)
        c = APIClient()
        c.force_authenticate(User.objects.create_superuser("u"))
        r = c.get(f"/api/analytics/overview/?from={day}&to={day}")
        self.assertEqual(r.status_code, 200)
        k = r.json()["kpis"]["current"]
        self.assertEqual((k["total"], k["completed"], k["no_show"], k["cancelled"]), (4, 2, 1, 1))
        self.assertEqual(k["no_show_rate"], 33.3)   # 1 of 3 appointments that were actually due
        self.assertEqual(k["cancel_rate"], 25.0)
        self.assertEqual(len(r.json()["daily"]), 1)
        self.assertEqual([(h["hour"], h["n"]) for h in r.json()["heatmap"]], [(9, 3)])  # cancelled excluded
        self.assertEqual(c.get("/api/analytics/overview/?from=2020-01-01&to=2026-01-01").status_code, 400)
