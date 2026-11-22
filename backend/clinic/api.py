from datetime import datetime, time, timedelta

from django.contrib.auth import authenticate, login, logout
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.permissions import AllowAny
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from django.conf import settings

from . import demo, services
from .permissions import ADMIN, DOCTOR, RECEPTIONIST, HasRole, doctor_id_of, role_of
from .models import Appointment, Doctor, Patient, QueueEntry


ALL_ROLES = (ADMIN, DOCTOR, RECEPTIONIST)


class AppointmentSerializer(serializers.ModelSerializer):
    start = serializers.DateTimeField(source="start_at", read_only=True)
    end = serializers.DateTimeField(source="end_at", read_only=True)
    doctor_name = serializers.SerializerMethodField()
    patient_name = serializers.CharField(source="patient.name", read_only=True)
    queue_entry = serializers.SerializerMethodField()

    class Meta:
        model = Appointment
        fields = ["id", "doctor", "doctor_name", "patient", "patient_name",
                  "start", "end", "status", "reason", "queue_entry"]

    def get_doctor_name(self, obj):
        return str(obj.doctor)

    def get_queue_entry(self, obj):
        q = getattr(obj, "queue_entry", None)
        return {"id": q.pk, "token": q.token_number, "status": q.status} if q else None


class BookingInput(serializers.Serializer):
    doctor = serializers.PrimaryKeyRelatedField(queryset=Doctor.objects.all())
    patient = serializers.PrimaryKeyRelatedField(queryset=Patient.objects.all())
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    reason = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, data):
        if data["end"] <= data["start"]:
            raise serializers.ValidationError("end must be after start")
        return data


class AppointmentListCreate(APIView):
    permission_classes = [HasRole]
    roles = {"GET": (ADMIN, DOCTOR, RECEPTIONIST), "POST": (ADMIN, RECEPTIONIST)}
    def get(self, request):
        qs = (Appointment.objects.select_related("doctor__user", "patient", "queue_entry")
              .order_by("start_at", "id"))
        if role_of(request.user) == DOCTOR:  # doctors only ever see their own patients
            qs = qs.filter(doctor_id=doctor_id_of(request.user))
        elif d := request.query_params.get("doctor"):
            qs = qs.filter(doctor_id=d)
        if day := parse_date(request.query_params.get("date", "")):  # clinic-local day
            if settings.DEMO_MODE and day == timezone.localdate():
                try:  # public demo site: make sure today always has a schedule
                    demo.create_day_schedule(day)
                except ValueError:
                    pass
            lo = timezone.make_aware(datetime.combine(day, time.min))
            qs = qs.filter(start_at__gte=lo, start_at__lt=lo + timedelta(days=1))
        return Response(AppointmentSerializer(qs[:300], many=True).data)

    def post(self, request):
        inp = BookingInput(data=request.data)
        inp.is_valid(raise_exception=True)
        try:
            appt = services.book_appointment(**inp.validated_data)
        except services.SlotTaken as e:
            return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)
        except services.InvalidSlot as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(AppointmentSerializer(appt).data, status=status.HTTP_201_CREATED)


class AppointmentCancel(APIView):
    permission_classes = [HasRole]
    roles = (ADMIN, RECEPTIONIST)
    def post(self, request, pk):
        get_object_or_404(Appointment, pk=pk)
        try:
            appt = services.cancel_appointment(pk)
        except services.QueueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)
        return Response(AppointmentSerializer(appt).data)


class CheckIn(APIView):
    permission_classes = [HasRole]
    roles = (ADMIN, RECEPTIONIST)
    def post(self, request):
        appt = get_object_or_404(Appointment, pk=request.data.get("appointment"))
        try:
            entry = services.check_in(appt)
        except services.QueueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)
        return Response({"entry_id": entry.pk, "token": entry.token_number}, status=201)


class QueueAction(APIView):
    action = None
    permission_classes = [HasRole]

    @property
    def roles(self):
        return ALL_ROLES if self.action == "no_show" else (ADMIN, DOCTOR)

    def post(self, request, pk):
        if role_of(request.user) == DOCTOR and not QueueEntry.objects.filter(
                pk=pk, doctor_id=doctor_id_of(request.user)).exists():
            return Response({"detail": "This patient is not in your queue."}, status=403)
        try:
            if self.action == "start":
                e = services.start_consultation(pk)
            elif self.action == "complete":
                e = services.finish_consultation(pk)
            else:
                e = services.finish_consultation(pk, no_show=True)
        except services.QueueError as err:
            return Response({"detail": str(err)}, status=status.HTTP_409_CONFLICT)
        return Response({"entry_id": e.pk, "status": e.status})


class DoctorQueue(APIView):
    permission_classes = [HasRole]
    roles = (ADMIN, DOCTOR, RECEPTIONIST)
    def get(self, request, pk):
        get_object_or_404(Doctor, pk=pk)
        if role_of(request.user) == DOCTOR and pk != doctor_id_of(request.user):
            return Response({"detail": "You can only view your own queue."}, status=403)
        return Response(services.doctor_queue_snapshot(pk))


class PatientQueuePosition(APIView):
    permission_classes = [HasRole]
    roles = (ADMIN, DOCTOR, RECEPTIONIST)
    def get(self, request, pk):
        entry = get_object_or_404(QueueEntry, pk=pk)
        if role_of(request.user) == DOCTOR and entry.doctor_id != doctor_id_of(request.user):
            return Response({"detail": "This patient is not in your queue."}, status=403)
        return Response(services.patient_position(entry))


def _user_json(u):
    return {"username": u.username, "is_staff": u.is_staff, "role": role_of(u), "doctor_id": doctor_id_of(u)}


@method_decorator(ensure_csrf_cookie, name="dispatch")
class Csrf(APIView):
    authentication_classes, permission_classes = [], [AllowAny]

    def get(self, request):
        return Response({"ok": True})


class Login(APIView):
    authentication_classes, permission_classes = [], [AllowAny]

    def post(self, request):
        user = authenticate(request, username=request.data.get("username", ""),
                            password=request.data.get("password", ""))
        if not user:
            return Response({"detail": "Incorrect username or password."}, status=400)
        login(request, user)
        return Response(_user_json(user))


class Logout(APIView):
    def post(self, request):
        logout(request)
        return Response(status=204)


class Me(APIView):
    def get(self, request):
        return Response(_user_json(request.user))


class DoctorList(APIView):
    permission_classes = [HasRole]
    roles = (ADMIN, DOCTOR, RECEPTIONIST)
    def get(self, request):
        qs = Doctor.objects.select_related("user", "specialty").order_by("id")
        if role_of(request.user) == DOCTOR:
            qs = qs.filter(pk=doctor_id_of(request.user))
        return Response([{"id": d.pk, "name": str(d), "specialty": d.specialty.name} for d in qs])


class PatientSearch(APIView):
    permission_classes = [HasRole]
    roles = (ADMIN, RECEPTIONIST)
    def get(self, request):
        q = request.query_params.get("q", "").strip()
        qs = Patient.objects.filter(name__icontains=q).order_by("name")[:15] if q else []
        return Response([{"id": p.pk, "name": p.name, "phone": p.phone} for p in qs])
