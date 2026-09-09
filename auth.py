"""
auth.py

Authentication (JWT-based) and role-based access control.

Passwords are hashed with werkzeug's PBKDF2-based generate_password_hash
(never stored in plaintext). Sessions are stateless JWTs so the API
doesn't need server-side session storage -- fits a REST API better than
cookie sessions, and is what the resume bullet ("secure user
authentication") is describing.
"""

import functools
import datetime

import jwt
from flask import request, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash

SECRET_KEY = "dev-secret-change-in-production"  # noqa: S105 — demo project, not for real deployment
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRY_HOURS = 8


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return check_password_hash(password_hash, password)


def generate_token(user_id: int, username: str, role: str) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "user_id": user_id,
        "username": username,
        "role": role,
        "exp": now + datetime.timedelta(hours=TOKEN_EXPIRY_HOURS),
        "iat": now,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])


def _extract_token_from_header() -> str | None:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[len("Bearer "):]
    return None


def require_auth(func):
    """Decorator: rejects the request unless a valid JWT is present, and
    stashes the decoded claims on flask.g.user for the view to use."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        token = _extract_token_from_header()
        if not token:
            return jsonify({"error": "Missing bearer token"}), 401
        try:
            g.user = decode_token(token)
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        return func(*args, **kwargs)
    return wrapper


def require_role(*allowed_roles):
    """Decorator: further restricts an already-authenticated route to
    specific roles. Must be applied INSIDE @require_auth (closer to the
    function) so g.user is already populated."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if g.user.get("role") not in allowed_roles:
                return jsonify({"error": "Forbidden: insufficient role"}), 403
            return func(*args, **kwargs)
        return wrapper
    return decorator
