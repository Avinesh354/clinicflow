from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from clinic.models import Appointment, AppointmentSlot, Doctor, Patient, Specialty


class RefreshTodayTests(TestCase):
    def setUp(self):
        U, spec = get_user_model(), Specialty.objects.create(name="GP")
        for i in range(2):
            Doctor.objects.create(user=U.objects.create_user(f"d{i}"), specialty=spec)
        for i in range(3):
            Patient.objects.create(name=f"P{i}")

    def run_cmd(self, day):
        call_command("refresh_today", date=day, stdout=StringIO())

    def test_adds_a_schedule_once(self):
        day = (timezone.localdate() + timedelta(days=3)).isoformat()
        self.run_cmd(day)
        n = Appointment.objects.count()
        self.assertGreater(n, 10)
        self.assertEqual(AppointmentSlot.objects.count(), n)  # every appointment holds its slot
        self.run_cmd(day)  # second run must add nothing
        self.assertEqual(Appointment.objects.count(), n)

    def test_needs_seed_data(self):
        Patient.objects.all().delete()
        with self.assertRaises(CommandError):
            self.run_cmd(timezone.localdate().isoformat())


class DemoModeTests(TestCase):
    def setUp(self):
        U = get_user_model()
        Doctor.objects.create(user=U.objects.create_user("dd"), specialty=Specialty.objects.create(name="GP"))
        Patient.objects.create(name="P")
        self.admin = U.objects.create_superuser("adm")

    def list_today(self):
        from rest_framework.test import APIClient
        c = APIClient()
        c.force_authenticate(self.admin)
        return c.get(f"/api/appointments/?date={timezone.localdate().isoformat()}").json()

    def test_off_by_default_so_real_data_is_never_invented(self):
        self.assertEqual(self.list_today(), [])

    def test_on_creates_today_once(self):
        from django.test import override_settings
        with override_settings(DEMO_MODE=True):
            first = self.list_today()
            self.assertGreater(len(first), 5)
            self.assertEqual(len(self.list_today()), len(first))  # second visit adds nothing
