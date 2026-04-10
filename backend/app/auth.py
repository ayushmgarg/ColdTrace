from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from datetime import UTC, datetime, timedelta

from fastapi import Header, HTTPException, status

from .config import settings


ROLE_ADMIN = "admin"
ROLE_MANAGER = "vaccine_manager"
ROLE_SUPERVISOR = "supervisor"
ROLE_VACCINATOR = "vaccinator"


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000).hex()


def create_password_record(password: str) -> tuple[str, str]:
    salt = secrets.token_hex(16)
    return salt, hash_password(password, salt)


def verify_password(password: str, salt: str, password_hash: str) -> bool:
    return secrets.compare_digest(hash_password(password, salt), password_hash)


def create_access_token(user: dict) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.token_ttl_minutes)
    payload = {
        "sub": user["id"],
        "email": user["email"],
        "role": user["role"],
        "facility_id": user.get("assigned_facility_id"),
        "exp": int(expires_at.timestamp()),
    }
    header_segment = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_segment = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_segment}.{payload_segment}".encode("utf-8")
    signature = hmac.new(settings.jwt_secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header_segment}.{payload_segment}.{_b64url_encode(signature)}"


def decode_access_token(token: str) -> dict:
    try:
        header_segment, payload_segment, signature_segment = token.split(".")
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token format") from error

    signing_input = f"{header_segment}.{payload_segment}".encode("utf-8")
    expected_signature = hmac.new(settings.jwt_secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    provided_signature = _b64url_decode(signature_segment)
    if not secrets.compare_digest(expected_signature, provided_signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token signature")

    payload = json.loads(_b64url_decode(payload_segment).decode("utf-8"))
    if int(payload["exp"]) < int(datetime.now(UTC).timestamp()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    return payload


def seed_default_users(connection: sqlite3.Connection) -> None:
    count = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if count:
        return

    seeded = [
        (
            "USR-ADMIN-001",
            "Ayush Admin",
            "admin@coldtrace.local",
            ROLE_ADMIN,
            None,
            "+91-90000-10001",
            settings.demo_admin_password,
        ),
        (
            "USR-MANAGER-001",
            "Regional Vaccine Manager",
            "manager@coldtrace.local",
            ROLE_MANAGER,
            "FAC-MUM-HUB",
            "+91-90000-10002",
            settings.demo_manager_password,
        ),
        (
            "USR-SUPERVISOR-001",
            "District Supervisor",
            "supervisor@coldtrace.local",
            ROLE_SUPERVISOR,
            "FAC-PUNE-TRANSIT",
            "+91-90000-10003",
            settings.demo_supervisor_password,
        ),
        (
            "USR-VACCINATOR-001",
            "Field Vaccinator",
            "vaccinator@coldtrace.local",
            ROLE_VACCINATOR,
            "FAC-NASHIK-CLINIC",
            "+91-90000-10004",
            settings.demo_vaccinator_password,
        ),
    ]

    for user_id, full_name, email, role, assigned_facility_id, phone_number, password in seeded:
        salt, password_hash = create_password_record(password)
        connection.execute(
            """
            INSERT INTO users (
                id, full_name, email, role, assigned_facility_id, phone_number, password_salt,
                password_hash, is_active, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
            """,
            (user_id, full_name, email, role, assigned_facility_id, phone_number, salt, password_hash),
        )


def authenticate_user(connection: sqlite3.Connection, email: str, password: str) -> dict | None:
    row = connection.execute(
        """
        SELECT id, full_name, email, role, assigned_facility_id, phone_number, password_salt, password_hash, is_active
        FROM users
        WHERE lower(email) = lower(?)
        """,
        (email,),
    ).fetchone()
    if not row or not row["is_active"]:
        return None
    if not verify_password(password, row["password_salt"], row["password_hash"]):
        return None
    return dict(row)


def fetch_user_by_id(connection: sqlite3.Connection, user_id: str) -> dict | None:
    row = connection.execute(
        """
        SELECT id, full_name, email, role, assigned_facility_id, phone_number, is_active
        FROM users
        WHERE id = ?
        """,
        (user_id,),
    ).fetchone()
    return dict(row) if row else None


def require_roles(*roles: str):
    async def dependency(authorization: str | None = Header(default=None)) -> dict:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
        token = authorization.split(" ", 1)[1].strip()
        payload = decode_access_token(token)
        role = payload.get("role")
        if roles and role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return payload

    return dependency

