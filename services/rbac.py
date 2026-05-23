"""RBAC — rôles workspace (E3)."""

from __future__ import annotations

from typing import Iterable

ROLE_HIERARCHY = ("viewer", "editor", "admin", "owner")

PERMISSIONS: dict[str, set[str]] = {
    "viewer": {"read"},
    "editor": {"read", "write", "publish"},
    "admin": {"read", "write", "publish", "accounts", "users"},
    "owner": {"read", "write", "publish", "accounts", "users", "billing"},
}


def role_allows(role: str, permission: str) -> bool:
    perms: set[str] = set()
    if role in ROLE_HIERARCHY:
        idx = ROLE_HIERARCHY.index(role)
        for r in ROLE_HIERARCHY[: idx + 1]:
            perms |= PERMISSIONS.get(r, set())
    return permission in perms


def get_user_role(user_id: str, workspace_id: str) -> str:
    from storage.database import Database

    with Database().connect() as conn:
        row = conn.execute(
            "SELECT role FROM workspace_members WHERE workspace_id = ? AND user_id = ?",
            (workspace_id, user_id),
        ).fetchone()
    if row:
        return str(row["role"])
    return "admin"  # bootstrap default


def require_permission(ctx: dict, permission: str) -> None:
    from fastapi import HTTPException

    role = ctx.get("role") or "admin"
    if ctx.get("auth") == "api_key":
        return
    if not role_allows(role, permission):
        raise HTTPException(status_code=403, detail=f"Permission refusée: {permission}")
