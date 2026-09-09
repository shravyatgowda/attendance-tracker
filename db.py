"""db.py — connection helper, mirrors the pattern used in the DJ booking project."""

import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, isolation_level=None, timeout=10)
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL mode allows concurrent readers alongside a writer, which matters
    # here since the peak-hour scenario is many check-ins (writes) while
    # an admin dashboard is simultaneously reading today's attendance.
    conn.execute("PRAGMA journal_mode = WAL")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str):
    conn = get_connection(db_path)
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())
    conn.close()
