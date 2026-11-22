from django.contrib import admin
from .models import Appointment, Doctor, Patient, QueueEntry, Specialty

for m in (Specialty, Doctor, Patient, Appointment, QueueEntry):
    admin.site.register(m)
