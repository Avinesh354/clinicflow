"""Add demo appointments for today (or --date) without touching existing data."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from clinic.demo import create_day_schedule


class Command(BaseCommand):
    help = "Create demo appointments for today so the queue screens are never empty. Safe to re-run."

    def add_arguments(self, p):
        p.add_argument("--date", help="YYYY-MM-DD (default: today, clinic time)")
        p.add_argument("--doctors", type=int, default=6, help="how many doctors get a schedule")

    def handle(self, *a, **o):
        day = date.fromisoformat(o["date"]) if o["date"] else datetime.now(ZoneInfo(settings.TIME_ZONE)).date()
        try:
            added, skipped = create_day_schedule(day, o["doctors"])
        except ValueError as exc:
            raise CommandError(str(exc))
        self.stdout.write(self.style.SUCCESS(
            f"{day}: added {added} appointments; {skipped} doctor(s) already had a schedule."))
