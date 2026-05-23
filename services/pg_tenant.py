"""Contexte tenant Postgres — SET LOCAL sur la bonne connexion (fix RLS)."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from config import settings


@contextmanager
def tenant_cursor(tenant_id: str | None = None) -> Iterator:
    """Curseur PG avec app.tenant_id défini pour la durée de la transaction."""
    from storage.postgres import postgres_configured

    if not postgres_configured():
        raise RuntimeError("Postgres non configuré")
    from storage.postgres_backend import pg_cursor

    tid = tenant_id or settings.default_tenant_id
    with pg_cursor() as cur:
        cur.execute("SELECT set_config('app.tenant_id', %s, true)", (tid,))
        yield cur
