"""Create a login for every role so each screen can be tried. Development only."""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError

from clinic.models import Doctor
from clinic.permissions import RECEPTIONIST

DEFAULT_PASSWORD = "clinic123"


class Command(BaseCommand):
    help = "Set demo passwords: reception1 (receptionist) and every seeded doctor login."

    def add_arguments(self, p):
        p.add_argument("--password", help="required when DEBUG is off (a public demo site)")

    def handle(self, *a, **o):
        if not settings.DEBUG and not o["password"]:
            raise CommandError("DEBUG is off: pass --password to confirm you want shared demo logins.")
        PASSWORD = o["password"] or DEFAULT_PASSWORD
        User = get_user_model()
        group, _ = Group.objects.get_or_create(name=RECEPTIONIST)
        r, _ = User.objects.get_or_create(username="reception1")
        r.set_password(PASSWORD); r.save(); r.groups.add(group)
        doctors = list(Doctor.objects.select_related("user").order_by("id"))
        for d in doctors:
            d.user.set_password(PASSWORD); d.user.save()
        self.stdout.write(self.style.SUCCESS(f"Password for all demo logins: {PASSWORD}"))
        self.stdout.write("  receptionist : reception1")
        for d in doctors[:6]:
            self.stdout.write(f"  doctor       : {d.user.username}  ({d})")
        self.stdout.write("  admin        : your own superuser")
