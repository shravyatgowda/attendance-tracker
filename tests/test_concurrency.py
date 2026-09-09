"""
test_concurrency.py

Two real concurrency scenarios, run with actual threads and actual
database connections (not mocked):

1. PEAK-HOUR THROUGHPUT: many DIFFERENT users check in at the same
   moment (the real "9 AM rush" scenario the resume bullet describes).
   We measure actual throughput and confirm every check-in lands
   correctly with no lost writes.

2. DUPLICATE CHECK-IN RACE: the SAME user's check-in request fires from
   multiple threads at once (e.g. a flaky client retrying, or a double
   click). Confirms the UNIQUE constraint + transaction lets exactly
   one succeed.

Run directly:
    python tests/test_concurrency.py
"""

import sys
import threading
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from db import get_connection, init_db
from attendance_service import check_in, AlreadyCheckedInError

DB_PATH = "test_concurrency_attendance.db"


def scenario_1_peak_hour_throughput(num_users: int = 100):
    Path(DB_PATH).unlink(missing_ok=True)
    for suffix in ("-wal", "-shm"):
        Path(DB_PATH + suffix).unlink(missing_ok=True)
    init_db(DB_PATH)

    conn = get_connection(DB_PATH)
    conn.execute("BEGIN")
    for i in range(1, num_users + 1):
        conn.execute(
            "INSERT INTO users (username, password_hash, full_name, role) VALUES (?, 'x', ?, 'employee')",
            (f"peakuser{i}", f"Peak User {i}"),
        )
    conn.execute("COMMIT")
    conn.close()

    results = []
    lock = threading.Lock()

    def worker(user_id):
        conn = get_connection(DB_PATH)
        try:
            check_in(conn, user_id=user_id)
            with lock:
                results.append(("SUCCESS", user_id))
        except Exception as e:
            with lock:
                results.append((f"ERROR: {e}", user_id))
        finally:
            conn.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(1, num_users + 1)]

    start = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.perf_counter() - start

    successes = [r for r in results if r[0] == "SUCCESS"]
    errors = [r for r in results if r[0] != "SUCCESS"]

    conn = get_connection(DB_PATH)
    row_count = conn.execute("SELECT COUNT(*) as c FROM attendance").fetchone()["c"]
    conn.close()

    print(f"\n[Scenario 1] {num_users} DIFFERENT users checking in simultaneously (peak-hour rush)")
    print(f"  Completed in {elapsed*1000:.1f} ms ({num_users/elapsed:.0f} check-ins/sec)")
    print(f"  Successful: {len(successes)}, Errors: {len(errors)}")
    print(f"  Rows actually in DB: {row_count}")

    assert len(successes) == num_users, f"Expected all {num_users} to succeed, got {len(successes)}"
    assert row_count == num_users, f"Expected {num_users} rows, found {row_count}"
    print("  PASSED: all concurrent check-ins recorded correctly, none lost.")


def scenario_2_duplicate_checkin_race(num_threads: int = 15):
    Path(DB_PATH).unlink(missing_ok=True)
    for suffix in ("-wal", "-shm"):
        Path(DB_PATH + suffix).unlink(missing_ok=True)
    init_db(DB_PATH)

    conn = get_connection(DB_PATH)
    conn.execute(
        "INSERT INTO users (username, password_hash, full_name, role) VALUES ('raceuser', 'x', 'Race User', 'employee')"
    )
    conn.close()

    results = []
    lock = threading.Lock()

    def worker():
        conn = get_connection(DB_PATH)
        try:
            check_in(conn, user_id=1)
            with lock:
                results.append("SUCCESS")
        except AlreadyCheckedInError:
            with lock:
                results.append("REJECTED")
        except Exception as e:
            with lock:
                results.append(f"ERROR: {e}")
        finally:
            conn.close()

    threads = [threading.Thread(target=worker) for _ in range(num_threads)]
    start = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.perf_counter() - start

    successes = [r for r in results if r == "SUCCESS"]
    rejected = [r for r in results if r == "REJECTED"]
    errors = [r for r in results if r not in ("SUCCESS", "REJECTED")]

    conn = get_connection(DB_PATH)
    row_count = conn.execute("SELECT COUNT(*) as c FROM attendance WHERE user_id = 1").fetchone()["c"]
    conn.close()

    print(f"\n[Scenario 2] {num_threads} threads racing to check in the SAME user for the SAME day")
    print(f"  Completed in {elapsed*1000:.1f} ms")
    print(f"  Successful: {len(successes)}, Correctly rejected: {len(rejected)}, Errors: {len(errors)}")
    print(f"  Rows actually in DB for this user: {row_count}")

    assert len(successes) == 1, f"Expected exactly 1 success, got {len(successes)}"
    assert len(rejected) == num_threads - 1
    assert row_count == 1, f"Expected exactly 1 attendance row, found {row_count}"
    print("  PASSED: exactly one check-in recorded, no duplicate rows despite the race.")

    Path(DB_PATH).unlink(missing_ok=True)
    for suffix in ("-wal", "-shm"):
        Path(DB_PATH + suffix).unlink(missing_ok=True)


if __name__ == "__main__":
    scenario_1_peak_hour_throughput(num_users=100)
    scenario_2_duplicate_checkin_race(num_threads=15)
