# ClinicFlow

Clinic scheduling, a live patient queue, and an operations dashboard.
**Django 5.2 · MySQL / MariaDB · React (Vite)**

The interesting part is correctness under concurrency: double-booking is impossible at the
database level, and each doctor can have only one patient inside at a time. Both rules are
enforced by MySQL itself and proven by parallel-request tests.

> All data is synthetic (generated names, fake phone numbers). Never load real patient data.

## Live demo
**https://YOUR-ACCOUNT.alwaysdata.net** (replace this after you deploy; see [DEPLOY.md](DEPLOY.md))
Sign in as `reception1` or `doctor1` with the demo password you set. Data is synthetic and may be reset at any time.

## Screenshots
| Dashboard | Live queue | Appointments |
|---|---|---|
| ![Dashboard](docs/screenshots/dashboard.png) | ![Live queue](docs/screenshots/queue.png) | ![Appointments](docs/screenshots/appointments.png) |

## What it does
- **Scheduling:** book, cancel and check in patients on a 20-minute grid. Overlaps are rejected.
- **Live queue:** each check-in gets a per-doctor, per-day token. The doctor calls patients in and completes consultations; screens refresh every 5 seconds with an estimated wait.
- **Dashboard (admin):** appointment volume, no-show and cancellation rates, slot utilization, a weekday-by-hour heatmap and per-doctor figures, each compared with the previous period.
- **Roles:** admin, receptionist and doctor, enforced on the server (a doctor cannot touch another doctor's patients).

## Engineering decisions
MySQL has no exclusion constraints or partial unique indexes, so the guarantees are built differently:

| Rule | How it is enforced |
|---|---|
| No overlapping appointments | A slot-occupancy table with `UNIQUE(doctor, slot_start)`; booking inserts the appointment and its slots in one transaction, and a duplicate-key error rolls everything back |
| One patient in consultation per doctor | A stored generated column (doctor id while in consultation, else NULL) with a `UNIQUE` index |
| Unique tokens under concurrent check-ins | A row lock on the doctor plus `UNIQUE(doctor, date, token)` |
| Valid time range | `CHECK (end_at > start_at)` |

Tested on MySQL 8.0 and MariaDB 10.11: all 22 tests, plus direct attempts to break each rule with raw inserts.

Trade-off: appointments are whole multiples of the slot length and must start on the grid.
Grid alignment is checked in the service layer; the database guarantees no two live appointments share a slot.

## Performance
Two indexes found with `EXPLAIN ANALYZE` cut the 30-day dashboard from about 118 ms to 26 ms on 100K appointments.
Method, caveats and a side effect are in [PERFORMANCE.md](PERFORMANCE.md).

## Run it locally
Requires Python 3.13, Node 20+, and MySQL 8.0.16+ (8.4 recommended) or MariaDB 10.6+.
```sql
CREATE DATABASE clinicflow CHARACTER SET utf8mb4;
CREATE USER 'clinicflow'@'localhost' IDENTIFIED BY 'clinicflow';
GRANT ALL ON clinicflow.* TO 'clinicflow'@'localhost';
GRANT ALL ON `test\_%`.* TO 'clinicflow'@'localhost';
```
```bash
cd backend
python -m venv .venv && .venv\Scripts\activate      # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py seed                 # ~100K appointments, 20 doctors, 20K patients
python manage.py setup_demo_users     # dev only: reception1 and doctor logins, password clinic123
python manage.py runserver            # http://127.0.0.1:8000
```
In a second terminal:
```bash
cd frontend && npm install && npm run dev      # http://localhost:5173
```
Sign in with your superuser (admin), `reception1` (receptionist) or `doctor1` (doctor).
The demo data is dated, so on a new day run `python manage.py refresh_today` to add today's appointments.
Use `seed --reset` to wipe and rebuild everything.

## Tests and benchmarks
```bash
python manage.py test clinic          # 22 tests, including parallel booking and check-in
python manage.py bench --explain      # endpoint timings and query plans
```
CI (GitHub Actions) runs the backend tests against MySQL 8.4 and builds the frontend on every push.

## Roles
| | Admin | Receptionist | Doctor |
|---|---|---|---|
| Book / cancel / check in | yes | yes | no |
| Call in / complete consultation | yes | no | own patients |
| Mark no-show | yes | yes | own patients |
| See appointments and queues | all | all | own |
| Dashboard | yes | no | no |

## Not done yet
- Live URL: the deployment guide is in [DEPLOY.md](DEPLOY.md); add the link above once it is up.
- A daily rollup table for the 365-day dashboard view, which still reads most rows.
- Browser time zone is assumed to match the clinic's (India).
- Frontend has no automated tests.
