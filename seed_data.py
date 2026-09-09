"""seed_data.py — creates an admin and a batch of employee users for demo/testing."""

from db import get_connection, init_db
from auth import hash_password

DB_PATH = "attendance.db"


def seed(db_path: str = DB_PATH, num_employees: int = 30):
    init_db(db_path)
    conn = get_connection(db_path)

    conn.execute("BEGIN")
    conn.execute(
        "INSERT OR IGNORE INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
        ("admin", hash_password("admin123"), "System Admin", "admin"),
    )
    for i in range(1, num_employees + 1):
        username = f"employee{i}"
        conn.execute(
            "INSERT OR IGNORE INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
            (username, hash_password("password123"), f"Employee {i}", "employee"),
        )
    conn.execute("COMMIT")
    conn.close()
    print(f"Seeded 1 admin + {num_employees} employees into {db_path}")


if __name__ == "__main__":
    seed()
