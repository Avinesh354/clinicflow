from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from clinic import services
from clinic.models import Doctor, Patient, Specialty


class RoleTests(TestCase):
    def setUp(self):
        U = get_user_model()
        spec = Specialty.objects.create(name="GP")
        self.d1 = Doctor.objects.create(user=U.objects.create_user("d1"), specialty=spec)
        self.d2 = Doctor.objects.create(user=U.objects.create_user("d2"), specialty=spec)
        self.recep = U.objects.create_user("r")
        self.recep.groups.add(Group.objects.create(name="receptionist"))
        self.admin, self.nobody = U.objects.create_superuser("a"), U.objects.create_user("n")
        p = Patient.objects.create(name="Asha")
        t = timezone.localtime(timezone.now() + timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
        self.t = t
        book = lambda d: services.book_appointment(doctor=d, patient=p, start=t, end=t + timedelta(minutes=20))
        self.a1, self.a2 = book(self.d1), book(self.d2)
        self.e1, self.e2 = services.check_in(self.a1), services.check_in(self.a2)

    def as_(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c

    def test_me_reports_role(self):
        roles = {u.username: self.as_(u).get("/api/auth/me/").json()["role"]
                 for u in (self.admin, self.recep, self.d1.user, self.nobody)}
        self.assertEqual(roles, {"a": "admin", "r": "receptionist", "d1": "doctor", "n": None})

    def test_user_without_role_is_refused_everywhere(self):
        c = self.as_(self.nobody)
        for url in ("/api/appointments/", "/api/doctors/", f"/api/queue/doctor/{self.d1.pk}/", "/api/analytics/overview/"):
            self.assertEqual(c.get(url).status_code, 403, url)

    def test_receptionist_front_desk_only(self):
        c = self.as_(self.recep)
        self.assertEqual(c.get("/api/appointments/").status_code, 200)
        self.assertEqual(c.get("/api/patients/?q=asha").status_code, 200)
        self.assertEqual(c.post(f"/api/queue/{self.e1.pk}/start/").status_code, 403)     # can't consult
        self.assertEqual(c.post(f"/api/queue/{self.e1.pk}/complete/").status_code, 403)
        self.assertEqual(c.get("/api/analytics/overview/").status_code, 403)
        self.assertEqual(c.post(f"/api/queue/{self.e1.pk}/no-show/").status_code, 200)  # can mark no-show

    def test_doctor_sees_and_acts_only_on_own_patients(self):
        c = self.as_(self.d1.user)
        rows = c.get("/api/appointments/").json()
        self.assertEqual({r["doctor"] for r in rows}, {self.d1.pk})
        self.assertEqual([d["id"] for d in c.get("/api/doctors/").json()], [self.d1.pk])
        self.assertEqual(c.get(f"/api/queue/doctor/{self.d1.pk}/").status_code, 200)
        self.assertEqual(c.get(f"/api/queue/doctor/{self.d2.pk}/").status_code, 403)
        self.assertEqual(c.get(f"/api/queue/entry/{self.e2.pk}/").status_code, 403)
        self.assertEqual(c.post(f"/api/queue/{self.e2.pk}/start/").status_code, 403)     # other doctor's patient
        self.assertEqual(c.post(f"/api/queue/{self.e1.pk}/start/").status_code, 200)
        self.assertEqual(c.post(f"/api/queue/{self.e1.pk}/complete/").status_code, 200)
        self.assertEqual(c.post("/api/queue/check-in/", {"appointment": self.a1.pk}, format="json").status_code, 403)
        self.assertEqual(c.get("/api/patients/?q=a").status_code, 403)
        body = {"doctor": self.d1.pk, "patient": 1, "start": self.t.isoformat(), "end": (self.t + timedelta(minutes=20)).isoformat()}
        self.assertEqual(c.post("/api/appointments/", body, format="json").status_code, 403)
        self.assertEqual(c.post(f"/api/appointments/{self.a1.pk}/cancel/").status_code, 403)

    def test_admin_can_do_everything(self):
        c = self.as_(self.admin)
        self.assertEqual(c.get("/api/analytics/overview/").status_code, 200)
        self.assertEqual(c.post(f"/api/queue/{self.e2.pk}/start/").status_code, 200)
        self.assertEqual(c.get(f"/api/queue/doctor/{self.d1.pk}/").status_code, 200)
