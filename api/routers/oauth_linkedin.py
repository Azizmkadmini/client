"""OAuth LinkedIn — authorization + callback (Phase 5)."""

from __future__ import annotations

import json
import secrets
import urllib.parse
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

from api.deps import AuthContext
from config import settings

router = APIRouter(prefix="/oauth/linkedin", tags=["oauth"])

_SCOPES = "openid profile w_member_social r_member_postAnalytics"


def _token_path():
    return settings.path("data/oauth_linkedin.json")


@router.get("/status")
def oauth_status(ctx: AuthContext) -> dict[str, Any]:
    path = _token_path()
    if not path.exists():
        return {"configured": bool(settings.oauth_linkedin_client_id), "connected": False}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        connected = bool(data.get("access_token")) or bool(data.get("enc"))
        return {
            "configured": True,
            "connected": connected,
            "encrypted": bool(data.get("enc")),
        }
    except Exception:
        return {"configured": True, "connected": False}


@router.get("/authorize")
def authorize(ctx: AuthContext) -> dict[str, str]:
    if not settings.oauth_linkedin_client_id:
        raise HTTPException(status_code=503, detail="OAUTH_LINKEDIN_CLIENT_ID non configuré")
    state = secrets.token_urlsafe(16)
    redirect_uri = _redirect_uri()
    params = {
        "response_type": "code",
        "client_id": settings.oauth_linkedin_client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "scope": _SCOPES,
    }
    url = "https://www.linkedin.com/oauth/v2/authorization?" + urllib.parse.urlencode(params)
    _token_path().parent.mkdir(parents=True, exist_ok=True)
    pending = {"state": state, "tenant_id": ctx["tenant_id"]}
    _token_path().with_suffix(".pending.json").write_text(
        json.dumps(pending), encoding="utf-8"
    )
    return {"authorization_url": url}


@router.get("/callback")
def callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    if error:
        web = getattr(settings, "web_app_url", "") or "http://127.0.0.1:3000"
        return RedirectResponse(url=f"{web.rstrip('/')}/settings?oauth_error={urllib.parse.quote(error)}")
    if not code:
        raise HTTPException(status_code=400, detail="code manquant")
    pending_path = _token_path().with_suffix(".pending.json")
    if pending_path.exists():
        pending = json.loads(pending_path.read_text(encoding="utf-8"))
        if state and pending.get("state") != state:
            raise HTTPException(status_code=400, detail="state invalide")
    token = _exchange_code(code)
    path = _token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    from services.crypto import encrypt_text

    from services.secrets_store import store_secret

    raw = json.dumps(token)
    encrypted = encrypt_text(raw)
    path.write_text(json.dumps({"enc": encrypted}, indent=2), encoding="utf-8")
    store_secret(settings.default_tenant_id, "linkedin_oauth", raw)
    pending_path.unlink(missing_ok=True)
    web = getattr(settings, "web_app_url", "") or "http://127.0.0.1:3000"
    return RedirectResponse(url=f"{web.rstrip('/')}/settings?oauth=linkedin_ok")


def _redirect_uri() -> str:
    base = getattr(settings, "oauth_linkedin_redirect_uri", "") or "http://127.0.0.1:8000/api/v1/oauth/linkedin/callback"
    return base.strip()


def _exchange_code(code: str) -> dict[str, Any]:
    if not settings.oauth_linkedin_client_secret:
        raise HTTPException(status_code=503, detail="OAUTH_LINKEDIN_CLIENT_SECRET manquant")
    resp = httpx.post(
        "https://www.linkedin.com/oauth/v2/accessToken",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": _redirect_uri(),
            "client_id": settings.oauth_linkedin_client_id,
            "client_secret": settings.oauth_linkedin_client_secret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30.0,
    )
    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"LinkedIn token error: {resp.text}")
    data = resp.json()
    return {
        "access_token": data.get("access_token"),
        "expires_in": data.get("expires_in"),
        "refresh_token": data.get("refresh_token"),
        "scope": data.get("scope"),
    }
