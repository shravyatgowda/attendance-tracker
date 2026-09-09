import sys
import datetime
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parent.parent))

from db import get_connection, init_db
from auth import hash_password, verify_password, generate_token, decode_token
from attendance_service import check_in, get_daily_report, get_user_history, AlreadyCheckedInError

TEST_DB = "test_functional_attendance.db"


@pytest.fixture
def conn():
    Path(TEST_DB).unlink(missing_ok=True)
    for suffix in ("-wal", "-shm"):
        Path(TEST_DB + suffix).unlink(missing_ok=True)
    init_db(TEST_DB)
    c = get_connection(TEST_DB)
    c.execute(
        "INSERT INTO users (username, password_hash, full_name, role) VALUES ('alice', ?, 'Alice A', 'employee')",
        (hash_password("secret123"),),
    )
    c.execute(
        "INSERT INTO users (username, password_hash, full_name, role) VALUES ('bob', ?, 'Bob B', 'employee')",
        (hash_password("secret456"),),
    )
    c.execute(
        "INSERT INTO users (username, password_hash, full_name, role) VALUES ('admin1', ?, 'Admin One', 'admin')",
        (hash_password("adminpass"),),
    )
    yield c
    c.close()
    Path(TEST_DB).unlink(missing_ok=True)
    for suffix in ("-wal", "-shm"):
        Path(TEST_DB + suffix).unlink(missing_ok=True)


# --- Auth tests ---

def test_password_hash_and_verify_roundtrip():
    h = hash_password("mypassword")
    assert h != "mypassword"  # never stored in plaintext
    assert verify_password("mypassword", h) is True
    assert verify_password("wrongpassword", h) is False


def test_jwt_roundtrip_contains_claims():
    token = generate_token(user_id=5, username="alice", role="employee")
    claims = decode_token(token)
    assert claims["user_id"] == 5
    assert claims["username"] == "alice"
    assert claims["role"] == "employee"


# --- Attendance logic tests ---

def test_checkin_before_cutoff_is_present(conn):
    result = check_in(conn, user_id=1, when=datetime.datetime(2026, 9, 6, 9, 0, 0))
    assert result["status"] == "present"


def test_checkin_after_cutoff_is_late(conn):
    result = check_in(conn, user_id=1, when=datetime.datetime(2026, 9, 6, 9, 45, 0))
    assert result["status"] == "late"


def test_duplicate_checkin_same_day_rejected(conn):
    check_in(conn, user_id=1, when=datetime.datetime(2026, 9, 6, 9, 0, 0))
    with pytest.raises(AlreadyCheckedInError):
        check_in(conn, user_id=1, when=datetime.datetime(2026, 9, 6, 14, 0, 0))


def test_checkin_next_day_allowed_after_previous_day(conn):
    check_in(conn, user_id=1, when=datetime.datetime(2026, 9, 6, 9, 0, 0))
    result = check_in(conn, user_id=1, when=datetime.datetime(2026, 9, 7, 9, 0, 0))
    assert result["date"] == "2026-09-07"


def test_different_users_can_checkin_same_day(conn):
    r1 = check_in(conn, user_id=1, when=datetime.datetime(2026, 9, 6, 9, 0, 0))
    r2 = check_in(conn, user_id=2, when=datetime.datetime(2026, 9, 6, 9, 5, 0))
    assert r1["user_id"] != r2["user_id"]


def test_user_history_ordered_most_recent_first(conn):
    check_in(conn, user_id=1, when=datetime.datetime(2026, 9, 5, 9, 0, 0))
    check_in(conn, user_id=1, when=datetime.datetime(2026, 9, 6, 9, 0, 0))
    history = get_user_history(conn, user_id=1)
    assert history[0]["attendance_date"] == "2026-09-06"
    assert history[1]["attendance_date"] == "2026-09-05"


def test_daily_report_counts_present_late_absent_correctly(conn):
    check_in(conn, user_id=1, when=datetime.datetime(2026, 9, 6, 9, 0, 0))   # present
    check_in(conn, user_id=2, when=datetime.datetime(2026, 9, 6, 9, 45, 0))  # late
    # admin1 is role='admin' so excluded from the employee report entirely
    report = get_daily_report(conn, "2026-09-06")
    assert report["total_employees"] == 2  # only employees, not admin1
    assert report["present_count"] == 1
    assert report["late_count"] == 1
    assert report["absent_count"] == 0


def test_daily_report_marks_no_checkin_as_absent(conn):
    check_in(conn, user_id=1, when=datetime.datetime(2026, 9, 6, 9, 0, 0))
    report = get_daily_report(conn, "2026-09-06")
    assert report["absent_count"] == 1
    assert report["absent"][0]["username"] == "bob"
