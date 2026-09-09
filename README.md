# Attendance Tracker Web Application

A backend for automating daily attendance: employees check themselves
in via a REST API, admins get an automated daily present/late/absent
report, and the system is built to hold up correctly when many people
check in at once — the actual "9 AM rush" scenario, not just a
single-user demo.

## What "reduces latency for concurrent check-ins" actually means here

The naive approach — check if a user already checked in today, then
insert if not — has a race condition under load: two near-simultaneous
requests can both pass the check before either writes. This project
avoids that entirely by making the database schema itself the
concurrency control:

```sql
UNIQUE (user_id, attendance_date)
```

Combined with an explicit `BEGIN IMMEDIATE` transaction around the
insert, this means concurrent check-in attempts are resolved by the
database's own constraint enforcement — no manual locking, no polling,
and no window where a duplicate can sneak through.

## Real concurrency test results (not estimates)

`tests/test_concurrency.py` runs two scenarios with actual threads and
actual database connections:

**Scenario 1 — peak-hour rush (100 different users checking in at once):**
```
Completed in 376–2069 ms across repeated runs (varies with system load)
Successful: 100/100, Errors: 0
Rows actually in DB: 100
```
Every run: zero lost writes, all 100 check-ins land correctly.

**Scenario 2 — duplicate check-in race (15 threads, same user, same day):**
```
Successful: 1, Correctly rejected: 14, Errors: 0
Rows actually in DB for this user: 1
```
Run repeatedly with the same result every time: exactly one check-in
wins, the other 14 get a clean `409 Conflict`, and the database never
ends up with more than one row.

**Caveat**: throughput numbers vary noticeably run-to-run in this dev
environment (48–266 check-ins/sec observed) since it's a shared sandbox
machine, not a dedicated benchmark host — the meaningful, consistent
result is *zero lost or duplicate writes across every run*, not a
specific throughput figure.

## Auth & RBAC

- Passwords hashed with Werkzeug's PBKDF2-based hasher — never stored
  or logged in plaintext (verified in `tests/test_attendance.py`).
- Stateless JWT auth (`PyJWT`), so the API doesn't need server-side
  session storage — a token carries `user_id`, `username`, and `role`.
- Two roles: `employee` (can check themselves in, view their own
  history) and `admin` (can additionally pull the daily report for
  everyone). Enforced via `@require_auth` + `@require_role("admin")`
  decorators — verified with real requests: employees get `403` on
  `/api/report`, unauthenticated requests get `401`.

## Project structure

```
attendance-tracker/
├── schema.sql              # users, attendance tables + indexes
├── db.py                   # connection helper (WAL mode enabled)
├── auth.py                 # password hashing, JWT, RBAC decorators
├── attendance_service.py   # check-in logic + daily report generation
├── seed_data.py             # creates 1 admin + N employees
├── app.py                  # Flask REST API
├── templates/index.html     # login + check-in dashboard
├── static/{style.css,script.js}
├── tests/
│   ├── test_attendance.py       # 10 functional tests (pytest)
│   └── test_concurrency.py      # real multi-threaded load test
└── requirements.txt
```

## API reference

| Method | Endpoint         | Auth        | Description                          |
|--------|------------------|-------------|---------------------------------------|
| POST   | `/api/login`     | none        | Returns a JWT on valid credentials    |
| POST   | `/api/checkin`   | user token  | Records today's check-in for the caller |
| GET    | `/api/history`   | user token  | Caller's own attendance history       |
| GET    | `/api/report`    | admin token | Present/late/absent counts for a date |

## Setup & run

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

python seed_data.py    # creates attendance.db with 1 admin + 30 employees
python app.py           # runs at http://localhost:5001
```

Default seeded credentials: `admin` / `admin123`, `employee1..employee30` / `password123`.

## Testing

```bash
pytest tests/test_attendance.py -v      # 10 functional + auth checks
python tests/test_concurrency.py         # peak-hour + duplicate-race load tests
```

## Design notes / trade-offs

- **Late cutoff is a fixed constant (9:30 AM)** rather than configurable
  per role/shift — a real system would store this per team/schedule.
- **JWT secret is a hardcoded dev value** (`auth.py`) — flagged clearly
  in-code as not production-ready; a real deployment would load it from
  an environment variable / secrets manager.
- **SQLite + WAL mode** was chosen for zero-setup local testing; the
  schema and queries are portable SQL, so migrating to MySQL/PostgreSQL
  for real concurrent production load mainly means swapping the
  connector in `db.py`.

## Possible extensions

- Add refresh tokens instead of a single 8-hour JWT.
- Add a "regularize attendance" admin workflow for manual corrections.
- Move report generation to a scheduled job (e.g. APScheduler or a cron
  task) that emails the daily report automatically at end-of-day.

## Tech stack

Python · Flask · SQLite (portable SQL) · PyJWT · Werkzeug · HTML/CSS/JS · pytest
