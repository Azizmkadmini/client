from __future__ import annotations

from typing import Annotated, Optional

from fastapi import Depends, Header, HTTPException, Request

from api.auth_jwt import decode_token
from config import settings


def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


def get_auth_context(
    request: Request,
    x_api_key: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
) -> dict:
    """API key (env ou table api_keys) OU Bearer JWT."""
    if x_api_key:
        if settings.api_key and x_api_key == settings.api_key:
            return {"tenant_id": settings.default_tenant_id, "auth": "api_key", "role": "owner"}
        try:
            from billing.service import ApiKeyService

            row = ApiKeyService().verify(x_api_key)
            if row:
                return {
                    "tenant_id": row["tenant_id"],
                    "auth": "api_key_db",
                    "key_name": row.get("name"),
                    "role": "admin",
                }
        except Exception:
            pass
        raise HTTPException(status_code=401, detail="Clé API invalide")
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        try:
            payload = decode_token(token)
            ctx = {
                "tenant_id": payload.get("tenant_id") or settings.default_tenant_id,
                "user_id": payload.get("sub"),
                "email": payload.get("email"),
                "auth": "jwt",
                "role": payload.get("role", "admin"),
            }
            # RLS: utiliser services.pg_tenant.tenant_cursor() dans les requêtes PG
            return ctx
        except Exception as exc:
            raise HTTPException(status_code=401, detail=f"JWT invalide: {exc}") from exc
    if not settings.api_key:
        return {"tenant_id": settings.default_tenant_id, "auth": "open", "role": "owner"}
    raise HTTPException(status_code=401, detail="API key ou Bearer token requis")


AuthContext = Annotated[dict, Depends(get_auth_context)]
