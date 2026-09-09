-- schema.sql
--
-- Attendance Tracker — schema
--
-- Design goals reflected in the resume bullets this project backs:
--   - "reducing processing latency for concurrent user check-ins":
--     the UNIQUE(user_id, date) constraint IS the concurrency control —
--     it lets the database itself reject a duplicate same-day check-in
--     instead of the application doing a slow read-then-write check.
--   - "query optimizations and indexing for rapid data retrieval during
--     peak morning hours": idx_attendance_date supports the "give me
--     everyone's status for today" query pattern (the actual peak-load
--     query — a dashboard refreshing during the morning check-in rush)
--     without a full table scan.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name     TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'employee' CHECK (role IN ('admin', 'employee')),
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS attendance (
    attendance_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(user_id),
    attendance_date TEXT NOT NULL,          -- ISO 'YYYY-MM-DD'
    check_in_time   TEXT NOT NULL,          -- ISO 'HH:MM:SS'
    status          TEXT NOT NULL CHECK (status IN ('present', 'late')),

    -- This single constraint is what makes "duplicate check-in" a
    -- database-enforced impossibility rather than an application-level
    -- race condition -- two concurrent check-in attempts for the same
    -- user/date can both reach the INSERT, but only one INSERT can
    -- succeed; the second raises IntegrityError and is caught cleanly.
    UNIQUE (user_id, attendance_date)
);

-- Speeds up the two hottest query patterns:
--   1. "who has/hasn't checked in today?" (admin dashboard, refreshed
--      repeatedly during the morning rush) -> idx_attendance_date
--   2. "show this user's attendance history" -> idx_attendance_user
CREATE INDEX IF NOT EXISTS idx_attendance_date ON attendance(attendance_date);
CREATE INDEX IF NOT EXISTS idx_attendance_user ON attendance(user_id);
