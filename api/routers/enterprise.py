"""Routes enterprise — flags, audit, KPIs, SSO stub (E3–E5)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException

from analytics.kpi_engine import compute_kpis
from api.deps import AuthContext
from services.audit import log_audit
from services.feature_flags import all_flags
from services.proxy_manager import ProxyManager
from services.rbac import require_permission

router = APIRouter(prefix="/enterprise", tags=["enterprise"])


@router.get("/feature-flags")
def feature_flags(ctx: AuthContext) -> dict[str, bool]:
    return all_flags(ctx["tenant_id"])


@router.get("/kpis")
def kpis(ctx: AuthContext) -> dict[str, Any]:
    require_permission(ctx, "read")
    return compute_kpis(ctx["tenant_id"])


@router.get("/audit")
def list_audit(ctx: AuthContext, limit: int = 50) -> dict[str, Any]:
    require_permission(ctx, "read")
    from storage.database import Database

    with Database().connect() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_logs WHERE tenant_id = ? ORDER BY created_at DESC LIMIT ?",
            (ctx["tenant_id"], limit),
        ).fetchall()
    return {"logs": [dict(r) for r in rows]}


@router.get("/proxies")
def list_proxies(ctx: AuthContext) -> dict[str, Any]:
    require_permission(ctx, "accounts")
    return {"proxies": ProxyManager().list_pool(ctx["tenant_id"])}


@router.get("/sso/config")
def sso_config(ctx: AuthContext) -> dict[str, Any]:
    """Stub OIDC — configurer AUTH_OIDC_* en prod."""
    from config import settings

    return {
        "enabled": bool(getattr(settings, "oidc_issuer", "")),
        "issuer": getattr(settings, "oidc_issuer", "") or None,
        "client_id": getattr(settings, "oidc_client_id", "") or None,
    }


@router.post("/gdpr/export")
def gdpr_export(ctx: AuthContext) -> dict[str, str]:
    require_permission(ctx, "admin")
    log_audit("gdpr.export", tenant_id=ctx["tenant_id"], actor_user_id=ctx.get("user_id"))
    return {"status": "queued", "message": "Export tenant — implémenter worker dédié"}


@router.post("/gdpr/delete")
def gdpr_delete(ctx: AuthContext) -> dict[str, str]:
    require_permission(ctx, "owner")
    log_audit("gdpr.delete_requested", tenant_id=ctx["tenant_id"], actor_user_id=ctx.get("user_id"))
    return {"status": "queued", "message": "Suppression tenant — confirmation requise"}
