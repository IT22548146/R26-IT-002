"""
middleware/auth_middleware.py
JWT authentication and role-based access control decorators.
"""

import os
import hashlib
import hmac
import json
import base64
from functools import wraps
from datetime import datetime, timedelta, timezone
from flask import request, jsonify, g

JWT_EXPIRY_HOURS = int(os.environ.get("JWT_EXPIRY_HOURS", 24))
SECRET_KEY       = os.environ.get("SECRET_KEY", "change-this-secret")


# ── Minimal JWT (no external library needed) ──────────────────────────────

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    pad = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * pad)


def generate_token(user_id: int, role: str, plant_id: str = None) -> str:
    header  = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    expiry  = (datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS)).isoformat()
    payload = _b64url_encode(json.dumps({
        "sub":      user_id,
        "role":     role,
        "plant_id": plant_id,
        "exp":      expiry,
    }).encode())
    sig = _b64url_encode(
        hmac.new(SECRET_KEY.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    )
    return f"{header}.{payload}.{sig}"


def decode_token(token: str) -> dict:
    """Returns payload dict or raises ValueError."""
    try:
        header, payload, sig = token.split(".")
    except ValueError:
        raise ValueError("Malformed token")

    expected_sig = _b64url_encode(
        hmac.new(SECRET_KEY.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    )
    if not hmac.compare_digest(sig, expected_sig):
        raise ValueError("Invalid token signature")

    data = json.loads(_b64url_decode(payload))
    if datetime.fromisoformat(data["exp"]) < datetime.now(timezone.utc):
        raise ValueError("Token expired")
    return data


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed


# ── Decorators ────────────────────────────────────────────────────────────

def require_auth(f):
    """Require a valid JWT in the Authorization header. Sets g.user_id, g.role, g.plant_id."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401
        token = auth[7:]
        try:
            data = decode_token(token)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 401
        g.user_id  = data["sub"]
        g.role     = data["role"]
        g.plant_id = data.get("plant_id")
        return f(*args, **kwargs)
    return decorated


def require_role(*roles):
    """Require specific role(s) in addition to auth. Usage: @require_role('Admin')"""
    def decorator(f):
        @wraps(f)
        @require_auth
        def decorated(*args, **kwargs):
            if g.role not in roles:
                return jsonify({"error": f"Access denied — requires role: {list(roles)}"}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator
