"""Feature flags YAML (E3)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from config import settings

_PATH = Path(__file__).resolve().parent.parent / "config" / "feature_flags.yaml"


def _load() -> dict[str, Any]:
    if not _PATH.exists():
        return {"flags": {}}
    return yaml.safe_load(_PATH.read_text(encoding="utf-8")) or {"flags": {}}


def is_enabled(flag: str, *, tenant_id: str | None = None) -> bool:
    cfg = _load().get("flags", {}).get(flag, {})
    if not cfg:
        return False
    if cfg.get("enabled") is False:
        return False
    allow = cfg.get("tenants")
    if allow and tenant_id and tenant_id not in allow:
        return False
    return bool(cfg.get("enabled", True))


def all_flags(tenant_id: str | None = None) -> dict[str, bool]:
    flags = _load().get("flags", {})
    return {name: is_enabled(name, tenant_id=tenant_id) for name in flags}
