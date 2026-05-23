"""Middleware tenant + audit (E0/E3)."""

from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from config import settings


class TenantContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.trace_id = request.headers.get("X-Trace-Id") or str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Trace-Id"] = request.state.trace_id
        return response


def set_postgres_tenant(tenant_id: str) -> None:
    try:
        from storage.postgres import postgres_configured
        from storage.postgres_backend import pg_connection

        if postgres_configured():
            with pg_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SET app.tenant_id = %s", (tenant_id,))
    except Exception:
        pass
