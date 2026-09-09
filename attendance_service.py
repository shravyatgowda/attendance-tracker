"""
attendance_service.py

Core attendance logic: check-in (with duplicate-check-in prevention
under concurrency) and daily report generation.
"""

import sqlite3
import datetime
from dataclasses import dataclass


class AlreadyCheckedInError(Exception):
    """Raised when a user has already checked in for the given date."""


LATE_CUTOFF = datetime.time(9, 30)  # after this time, status = 'late'


def _status_for_time(check_in_time: datetime.time) -> str:
    return "late" if check_in_time > LATE_CUTOFF else "present"


def check_in(conn: sqlite3.Connection, user_id: int, when: datetime.datetime | None = None) -> dict:
    """
    Record a check-in for `user_id` at `when` (defaults to now).

    Wrapped in an explicit transaction so the UNIQUE(user_id, date)
    constraint is the actual concurrency guard: if two requests for the
    same user race, the DB accepts exactly one INSERT and raises
    IntegrityError for the other, which we translate into a clean
    application-level error rather than a duplicate row.
    """
    when = when or datetime.datetime.now()
    date_str = when.strftime("%Y-%m-%d")
    time_str = when.strftime("%H:%M:%S")
    status = _status_for_time(when.time())

    try:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.execute(
            """
            INSERT INTO attendance (user_id, attendance_date, check_in_time, status)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, date_str, time_str, status),
        )
        conn.execute("COMMIT")
        return {
            "attendance_id": cursor.lastrowid,
            "user_id": user_id,
            "date": date_str,
            "check_in_time": time_str,
            "status": status,
        }
    except sqlite3.IntegrityError as e:
        conn.execute("ROLLBACK")
        raise AlreadyCheckedInError(
            f"User {user_id} has already checked in for {date_str}"
        ) from e


def get_user_history(conn: sqlite3.Connection, user_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT attendance_date, check_in_time, status
        FROM attendance
        WHERE user_id = ?
        ORDER BY attendance_date DESC
        """,
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_daily_report(conn: sqlite3.Connection, date_str: str) -> dict:
    """
    Automated daily report: who's present, who's late, who hasn't
    checked in at all -- the kind of report an admin would want auto
    generated at the end of each day.

    This is a single indexed query (idx_attendance_date) joined against
    the full user list, rather than N queries per user -- important
    for the "peak morning hours" performance angle: this same query
    pattern is what a live dashboard would poll repeatedly.
    """
    all_users = conn.execute(
        "SELECT user_id, username, full_name FROM users WHERE role = 'employee'"
    ).fetchall()

    checked_in = conn.execute(
        """
        SELECT user_id, check_in_time, status
        FROM attendance
        WHERE attendance_date = ?
        """,
        (date_str,),
    ).fetchall()
    checked_in_map = {row["user_id"]: dict(row) for row in checked_in}

    present, late, absent = [], [], []
    for user in all_users:
        record = checked_in_map.get(user["user_id"])
        entry = {"user_id": user["user_id"], "username": user["username"], "full_name": user["full_name"]}
        if record is None:
            absent.append(entry)
        elif record["status"] == "late":
            entry["check_in_time"] = record["check_in_time"]
            late.append(entry)
        else:
            entry["check_in_time"] = record["check_in_time"]
            present.append(entry)

    total = len(all_users)
    return {
        "date": date_str,
        "total_employees": total,
        "present_count": len(present),
        "late_count": len(late),
        "absent_count": len(absent),
        "present": present,
        "late": late,
        "absent": absent,
    }
