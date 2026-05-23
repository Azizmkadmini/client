"""
Import CSV leads + SQLite content vers PostgreSQL (Phase 3).

Usage:
  set STORAGE_BACKEND=postgres
  set DATABASE_URL=postgresql://...
  python scripts/migrate_all_to_postgres.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import settings
from storage.postgres import postgres_configured
from storage.postgres_backend import apply_all_schemas, import_csv_to_postgres


def main() -> int:
    if not postgres_configured():
        print("Configurez STORAGE_BACKEND=postgres et DATABASE_URL")
        return 1
    applied = apply_all_schemas()
    print("Schémas:", applied)
    csv = settings.path(settings.leads_csv)
    if csv.exists():
        n = import_csv_to_postgres(csv)
        print(f"Leads importés depuis CSV: {n}")
    import subprocess

    subprocess.check_call([sys.executable, str(ROOT / "scripts" / "migrate_content_to_postgres.py")])
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
