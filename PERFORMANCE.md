# Performance notes

Measured on 100,088 appointments (87,069 slot rows), MySQL 8.0, Django 5.2, 40 runs per endpoint after
3 warm-up runs, optimizer statistics refreshed before each run (`ANALYZE TABLE`).
**These numbers are from my test machine. Run `python manage.py bench` on yours and use your own.**

## Results (p50 latency, milliseconds)

| Endpoint | Before | After | Change | p95 before → after |
|---|---|---|---|---|
| Dashboard, last 30 days | 117.9 | 25.8 | -78% | 121.3 → 26.4 |
| Dashboard, last 90 days | 143.5 | 63.6 | -56% | 156.9 → 67 |
| Dashboard, last 365 days | 212.4 | 180.6 | -15% | 260.4 → 183 |
| Dashboard, 90 days, one doctor | 14.4 | 17 | +18% | 15.5 → 17.4 |
| Appointments list, one day | 33 | 7.4 | -78% | 35.5 → 9.5 |
| Live queue snapshot | 3.8 | 3.9 | +3% | 4.1 → 5.7 |

## What I found
`EXPLAIN ANALYZE` on the dashboard showed MySQL reading **all 100,088 rows** to answer a 30-day question
(`Index scan on clinic_appointment using appt_doctor_start_idx ... rows=100088`). The only index that
included the date started with `doctor`, so a query across all doctors could not jump to the date range.
The utilization query had the same problem on `clinic_appointmentslot` (87,069 rows scanned).

## What changed
Two indexes that lead with the date column (migrations 0002 and 0003):
- `appointment (start_at, doctor, status)`: range scan on date; aggregates come from the index alone.
- `appointment_slot (slot_start, doctor)`: same idea for the utilization query.

## Trade-offs and limits
- **The 365-day view barely improved** (~15%). It needs almost every row, so no index can avoid the work.
  The next step would be pre-aggregated daily rollup table, which I have not built.
- **The single-doctor dashboard got slightly slower** (a few milliseconds). I did not pin down which query
  is responsible. It was repeatable across runs, so I am reporting it as a real side effect.
- **Write cost was not measured.** Every extra index slows inserts and updates a little.
- **In-process timing.** Excludes network and browser rendering. Cache is warm. One machine, 100K rows;
  I have not tested at 1M rows.
- Run `ANALYZE TABLE` after bulk loads; stale statistics can make the optimizer choose badly.

## Reproduce
```
python manage.py migrate clinic 0001   # original indexes
python manage.py bench --runs 40 --json before.json
python manage.py migrate               # with the new indexes
python manage.py bench --runs 40 --json after.json
```
Add `--explain` to print the plan of the slowest query for each endpoint.
