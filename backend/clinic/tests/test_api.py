from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from clinic.models import Doctor, Patient, Specialty


class BookingApiTests(TestCase):
    def test_double_booking_returns_409(self):
        user = get_user_model().objects.create_superuser("recep")
        doc = Doctor.objects.create(user=get_user_model().objects.create_user("d"),
                                    specialty=Specialty.objects.create(name="GP"))
        p1, p2 = Patient.objects.create(name="A"), Patient.objects.create(name="B")
        c = APIClient()
        c.force_authenticate(user)
        s = timezone.localtime(timezone.now() + timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
        body = lambda p: {"doctor": doc.pk, "patient": p.pk, "start": s.isoformat(),
                          "end": (s + timedelta(minutes=20)).isoformat()}
        self.assertEqual(c.post("/api/appointments/", body(p1), format="json").status_code, 201)
        self.assertEqual(c.post("/api/appointments/", body(p2), format="json").status_code, 409)

    def test_off_grid_returns_400(self):
        user = get_user_model().objects.create_superuser("recep")
        doc = Doctor.objects.create(user=get_user_model().objects.create_user("d"),
                                    specialty=Specialty.objects.create(name="GP"))
        p = Patient.objects.create(name="A")
        c = APIClient()
        c.force_authenticate(user)
        s = timezone.localtime(timezone.now() + timedelta(days=1)).replace(minute=7, second=0, microsecond=0)
        r = c.post("/api/appointments/", {"doctor": doc.pk, "patient": p.pk, "start": s.isoformat(),
                                          "end": (s + timedelta(minutes=20)).isoformat()}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_requires_auth(self):
        self.assertEqual(APIClient().get("/api/appointments/").status_code, 403)


class AuthAndListTests(TestCase):
    def test_login_me_list_and_check_in_shape(self):
        from clinic import services
        get_user_model().objects.create_superuser("recep", password="pw12345!")
        c = APIClient()
        self.assertEqual(c.post("/api/auth/login/", {"username": "recep", "password": "x"}, format="json").status_code, 400)
        self.assertEqual(c.post("/api/auth/login/", {"username": "recep", "password": "pw12345!"}, format="json").status_code, 200)
        self.assertEqual(c.get("/api/auth/me/").json()["username"], "recep")
        doc = Doctor.objects.create(user=get_user_model().objects.create_user("d"),
                                    specialty=Specialty.objects.create(name="GP"))
        p = Patient.objects.create(name="Asha Rao")
        s = timezone.localtime(timezone.now()).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        a = services.book_appointment(doctor=doc, patient=p, start=s, end=s + timedelta(minutes=20))
        day = timezone.localtime(s).date().isoformat()
        row = c.get(f"/api/appointments/?date={day}").json()[0]
        self.assertEqual((row["patient_name"], row["queue_entry"]), ("Asha Rao", None))
        self.assertEqual(c.post("/api/queue/check-in/", {"appointment": a.pk}, format="json").status_code, 201)
        self.assertEqual(c.get(f"/api/appointments/?date={day}").json()[0]["queue_entry"]["token"], 1)
        self.assertEqual(c.get("/api/doctors/").json()[0]["specialty"], "GP")
        self.assertEqual(c.get("/api/patients/?q=asha").json()[0]["name"], "Asha Rao")
