"""JWT + utilisateurs locaux (bootstrap SaaS)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from config import settings
from storage.database import Database


def _secret() -> str:
    s = (getattr(settings, "jwt_secret", None) or "").strip()
    if not s:
        s = (settings.api_key or "dev-change-jwt-secret-in-env")
    return s


def _ensure_users_table() -> None:
    db = Database()
    db.migrate()
    with db.connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_users (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'admin',
                created_at TEXT NOT NULL
            )
            """
        )


def create_token(*, user_id: str, tenant_id: str, email: str, role: str = "admin") -> str:
    hours = int(getattr(settings, "jwt_expire_hours", 168) or 168)
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "email": email,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=hours),
    }
    return jwt.encode(payload, _secret(), algorithm="HS256")


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, _secret(), algorithms=["HS256"])


def bootstrap_user(email: str, password: str, *, tenant_id: str | None = None) -> dict[str, str]:
    import bcrypt

    _ensure_users_table()
    tid = tenant_id or settings.default_tenant_id
    uid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    db = Database()
    with db.connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO app_users (id, tenant_id, email, password_hash, role, created_at) VALUES (?, ?, ?, ?, 'admin', ?)",
            (uid, tid, email.lower(), pw_hash, now),
        )
    token = create_token(user_id=uid, tenant_id=tid, email=email)
    return {"user_id": uid, "tenant_id": tid, "access_token": token, "token_type": "bearer"}


def login_user(email: str, password: str) -> dict[str, str]:
    import bcrypt

    _ensure_users_table()
    db = Database()
    with db.connect() as conn:
        row = conn.execute(
            "SELECT id, tenant_id, email, password_hash FROM app_users WHERE email = ?",
            (email.lower(),),
        ).fetchone()
    if row is None:
        raise ValueError("Identifiants invalides")
    if not bcrypt.checkpw(password.encode(), row["password_hash"].encode()):
        raise ValueError("Identifiants invalides")
    token = create_token(user_id=row["id"], tenant_id=row["tenant_id"], email=row["email"])
    return {"access_token": token, "token_type": "bearer", "tenant_id": row["tenant_id"]}
