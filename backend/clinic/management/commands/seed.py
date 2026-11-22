"""Generate fake (synthetic) clinic data. Never use real patient data."""
import random
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Max
from faker import Faker

from clinic.models import Appointment, AppointmentSlot, Doctor, Patient, QueueEntry, Specialty

SPECIALTIES = ["General Medicine", "Pediatrics", "Cardiology", "Dermatology", "Orthopedics", "ENT"]

# Tamil-style names: mostly single names, some two-part ("Prem Kumar", "Anitha Devi").
M_SINGLE = """Suresh Ramesh Rajesh Karthik Vignesh Arun Ashok Balaji Bharath Chandran Dinesh Elango Ganesh Gokul Gopal
Hari Harish Jagan Kannan Kishore Lokesh Madhavan Mahesh Manoj Mohan Murali Murugan Muthu Naveen Nithin
Pandian Prakash Pradeep Praveen Prabhu Rajan Ravi Sakthi Saravanan Sathish Selvam Senthil Shankar Siva
Sriram Sundar Surya Thiru Udhay Vasanth Velu Venkat Vetri Vijay Vikram Vinoth Vivek Yuvaraj Anand Anbu
Gowtham Kumaran Mani Palani Santhosh""".split()
F_SINGLE = """Priya Divya Anitha Lakshmi Meena Kavitha Deepa Swathi Pooja Nisha Sneha Anjali Bhavana Chitra Gayathri
Harini Indira Janani Kalpana Keerthana Latha Madhavi Nandhini Padma Radha Revathi Saranya Shanthi Sowmya
Sudha Suganya Sunitha Tamilselvi Uma Vaishnavi Vidya Yamini Aarthi Bharathi Dhivya Jayanthi Kaveri Malini
Pavithra Shruthi Sangeetha Rekha Geetha Mythili Nithya Malathi Vasuki Banu Kala Jaya Vanitha Selvi""".split()
M_PREFIX = """Prem Senthil Arun Ravi Siva Muthu Vijay Mohan Suresh Ram Raja Anand Dinesh Karthik Santhosh Ganesh
Naveen Vinoth Saravana Bala Hari Vasanth Kumar Gopi Mahesh""".split()
M_SUFFIX = "Kumar Raj Prasad Babu Mani Nathan Shankar Chandran Anand Kannan".split()
F_PREFIX = """Anitha Kavitha Meena Radha Tamil Priya Deepa Revathi Geetha Sangeetha Lakshmi Saranya Divya Nithya
Gayathri Malathi Uma Vasuki Jaya Sudha Latha Banu Rekha Kala Mythili""".split()
F_SUFFIX = "Devi Kumari Rani Selvi Priya Lakshmi".split()
COMPOUND_SHARE = 0.4  # share of people with a two-part name
MALE_SHARE = 0.6  # 6:4 male:female


class Command(BaseCommand):
    help = "Seed doctors, patients and appointments (synthetic data)."

    def add_arguments(self, p):
        p.add_argument("--appointments", type=int, default=100_000)
        p.add_argument("--doctors", type=int, default=20)
        p.add_argument("--patients", type=int, default=20_000)
        p.add_argument("--seed", type=int, default=42)
        p.add_argument("--reset", action="store_true",
                       help="wipe appointments, queue, patients and seeded doctors first")

    @transaction.atomic
    def handle(self, *a, **o):
        User = get_user_model()
        if o["reset"]:
            QueueEntry.objects.all().delete()
            AppointmentSlot.objects.all().delete()
            Appointment.objects.all().delete()
            Doctor.objects.all().delete()
            Patient.objects.all().delete()
            User.objects.filter(username__regex=r"^doctor[0-9]+$", is_staff=False, is_superuser=False).delete()
        elif Appointment.objects.exists():
            raise CommandError("Already seeded. Run with --reset to wipe and reseed.")

        rnd, fake = random.Random(o["seed"]), Faker("en_IN")
        Faker.seed(o["seed"])
        tz = ZoneInfo(settings.TIME_ZONE)
        step = settings.CLINIC_SLOT_MINUTES

        def genders(n):  # exactly 60% male / 40% female, shuffled
            males = round(n * MALE_SHARE)
            g = ["M"] * males + ["F"] * (n - males)
            rnd.shuffle(g)
            return g

        def tamil_name(g):
            single, pre, suf = (M_SINGLE, M_PREFIX, M_SUFFIX) if g == "M" else (F_SINGLE, F_PREFIX, F_SUFFIX)
            if rnd.random() < COMPOUND_SHARE:
                while True:
                    a, b = rnd.choice(pre), rnd.choice(suf)
                    if a != b:
                        return f"{a} {b}"
            return rnd.choice(single)

        def phone():
            return f"+91 {rnd.choice('6789')}{rnd.randrange(10**4):04d} {rnd.randrange(10**5):05d}"

        specs = [Specialty.objects.get_or_create(name=n)[0] for n in SPECIALTIES]
        doctors, used = [], set()
        for i, g in enumerate(genders(o["doctors"])):
            while True:  # doctor names are unique so the dropdown is unambiguous
                name = tamil_name(g)
                if name not in used:
                    used.add(name)
                    break
            first, _, last = name.partition(" ")
            u, _ = User.objects.get_or_create(username=f"doctor{i+1}", defaults={
                "first_name": first, "last_name": last})
            doctors.append(Doctor.objects.get_or_create(user=u, defaults={"specialty": rnd.choice(specs)})[0])

        Patient.objects.bulk_create(
            [Patient(name=tamil_name(g), phone=phone(),
                     date_of_birth=fake.date_of_birth(minimum_age=1, maximum_age=90))
             for g in genders(o["patients"])], batch_size=5000)
        pids = list(Patient.objects.values_list("pk", flat=True))

        # MySQL's bulk_create doesn't return PKs, so assign them explicitly.
        next_id = (Appointment.objects.aggregate(m=Max("id"))["m"] or 0) + 1
        per_day = (8 * 60) // step  # 09:00-17:00
        appts, slots, day, target = [], [], datetime.now(tz).date() - timedelta(days=1), o["appointments"]
        while len(appts) < target:
            day -= timedelta(days=1)
            if day.weekday() >= 5:
                continue
            for d in doctors:
                for k in range(per_day):
                    if len(appts) >= target:
                        break
                    if rnd.random() < 0.25:  # not every slot is booked
                        continue
                    start = datetime.combine(day, time(9, 0), tz) + timedelta(minutes=step * k)
                    r = rnd.random()
                    st = "completed" if r < 0.75 else "no_show" if r < 0.87 else "cancelled"
                    aid = next_id + len(appts)
                    appts.append(Appointment(id=aid, doctor=d, patient_id=rnd.choice(pids), start_at=start,
                                             end_at=start + timedelta(minutes=step), status=st))
                    if st != "cancelled":  # cancelled appointments don't hold a slot
                        slots.append(AppointmentSlot(appointment_id=aid, doctor=d, slot_start=start))

        # Demo data for today so the queue screens have something to show.
        today = datetime.now(tz).date()
        for d in doctors[:6]:
            for k in range(per_day):
                if rnd.random() < 0.4:
                    continue
                start = datetime.combine(today, time(9, 0), tz) + timedelta(minutes=step * k)
                aid = next_id + len(appts)
                appts.append(Appointment(id=aid, doctor=d, patient_id=rnd.choice(pids), start_at=start,
                                         end_at=start + timedelta(minutes=step)))
                slots.append(AppointmentSlot(appointment_id=aid, doctor=d, slot_start=start))
        Appointment.objects.bulk_create(appts, batch_size=5000)
        AppointmentSlot.objects.bulk_create(slots, batch_size=5000)
        self.stdout.write(self.style.SUCCESS(
            f"Seeded {len(appts)} appointments ({len(slots)} slot rows), {len(doctors)} doctors."))
