"""Time the endpoints that matter. Run before and after a change, then compare.

Runs in-process through Django's test client, so it measures application + database time
(not network or browser rendering). Put your own machine's numbers on a resume, not mine.
"""
import json
import statistics
import time
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from clinic.models import Appointment, Doctor


class Command(BaseCommand):
    help = "Benchmark the dashboard, appointment list and queue endpoints."

    def add_arguments(self, p):
        p.add_argument("--runs", type=int, default=30)
        p.add_argument("--explain", action="store_true", help="show the plan of the slowest query per endpoint")
        p.add_argument("--json", help="also write results to this file")

    def handle(self, *a, **o):
        admin, _ = get_user_model().objects.get_or_create(
            username="bench_admin", defaults={"is_superuser": True, "is_staff": True})
        client = APIClient()
        client.force_authenticate(admin)
        today, doc = timezone.localdate(), Doctor.objects.order_by("id").first()
        span = lambda n: f"from={today - timedelta(n - 1)}&to={today}"
        targets = [
            ("Dashboard, last 30 days", f"/api/analytics/overview/?{span(30)}"),
            ("Dashboard, last 90 days", f"/api/analytics/overview/?{span(90)}"),
            ("Dashboard, last 365 days", f"/api/analytics/overview/?{span(365)}"),
            ("Dashboard, 90 days, one doctor", f"/api/analytics/overview/?{span(90)}&doctor={doc.pk}"),
            ("Appointments list, one day", f"/api/appointments/?date={today}"),
            ("Live queue snapshot", f"/api/queue/doctor/{doc.pk}/"),
        ]
        with connection.cursor() as cur:  # fresh optimizer statistics, so a new index is judged fairly
            cur.execute("ANALYZE TABLE clinic_appointment, clinic_appointmentslot, clinic_queueentry")
            cur.fetchall()
        rows = Appointment.objects.count()
        self.stdout.write(f"{rows:,} appointments | {o['runs']} runs each (after 3 warm-up runs)\n")
        self.stdout.write(f"{'endpoint':<34}{'p50 ms':>8}{'p95 ms':>8}{'queries':>9}{'db ms':>8}")
        results = []
        for name, url in targets:
            for _ in range(3):
                client.get(url)
            times = []
            for _ in range(o["runs"]):
                t = time.perf_counter()
                resp = client.get(url)
                times.append((time.perf_counter() - t) * 1000)
            assert resp.status_code == 200, (url, resp.status_code)
            with CaptureQueriesContext(connection) as ctx:
                client.get(url)
            times.sort()
            res = {"endpoint": name, "p50_ms": round(statistics.median(times), 1),
                   "p95_ms": round(times[max(0, int(len(times) * 0.95) - 1)], 1),
                   "queries": len(ctx), "db_ms": round(sum(float(q["time"]) for q in ctx.captured_queries) * 1000, 1)}
            results.append(res)
            self.stdout.write(f"{name:<34}{res['p50_ms']:>8}{res['p95_ms']:>8}{res['queries']:>9}{res['db_ms']:>8}")
            if o["explain"]:
                slow = max(ctx.captured_queries, key=lambda q: float(q["time"]))
                with connection.cursor() as cur:
                    cur.execute("EXPLAIN ANALYZE " + slow["sql"])
                    plan = cur.fetchone()[0]
                self.stdout.write("   slowest query plan:\n" + "\n".join("     " + l for l in plan.splitlines()[:7]))
        if o["json"]:
            json.dump({"appointments": rows, "results": results}, open(o["json"], "w"), indent=2)
