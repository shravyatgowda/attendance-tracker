"""
app.py

REST API for the attendance tracker.

Endpoints:
    POST /api/login                    -> returns JWT
    POST /api/checkin                  -> authenticated user checks themselves in
    GET  /api/history                  -> authenticated user's own attendance history
    GET  /api/report?date=YYYY-MM-DD   -> admin-only: daily report across all employees
    GET  /                             -> simple HTML dashboard (uses the API via JS)

Run with:
    python app.py
"""

import datetime

from flask import Flask, jsonify, request, render_template, g

from auth import generate_token, verify_password, require_auth, require_role
from attendance_service import check_in, get_user_history, get_daily_report, AlreadyCheckedInError
from db import get_connection, init_db

DB_PATH = "attendance.db"

app = Flask(__name__)
init_db(DB_PATH)


def db():
    return get_connection(DB_PATH)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(force=True, silent=True) or {}
    username = data.get("username")
    password = data.get("password")
    if not username or not password:
        return jsonify({"error": "username and password required"}), 400

    conn = db()
    user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()

    if user is None or not verify_password(password, user["password_hash"]):
        return jsonify({"error": "Invalid credentials"}), 401

    token = generate_token(user["user_id"], user["username"], user["role"])
    return jsonify({"token": token, "role": user["role"], "full_name": user["full_name"]})


@app.route("/api/checkin", methods=["POST"])
@require_auth
def checkin():
    conn = db()
    try:
        result = check_in(conn, user_id=g.user["user_id"])
        return jsonify(result), 201
    except AlreadyCheckedInError as e:
        return jsonify({"error": str(e)}), 409
    finally:
        conn.close()


@app.route("/api/history")
@require_auth
def history():
    conn = db()
    records = get_user_history(conn, user_id=g.user["user_id"])
    conn.close()
    return jsonify({"user_id": g.user["user_id"], "history": records})


@app.route("/api/report")
@require_auth
@require_role("admin")
def report():
    date_str = request.args.get("date") or datetime.date.today().isoformat()
    conn = db()
    result = get_daily_report(conn, date_str)
    conn.close()
    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True, port=5001)
