"""
Bootstrap AI Acquisition OS — tenant, user admin, schémas.

Usage:
  python scripts/bootstrap_saas.py --email admin@example.com --password secret
  python scripts/bootstrap_saas.py --postgres   # applique schémas PG
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from api.auth_jwt import bootstrap_user
from content.store import ContentStore


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", default="admin@local.dev")
    parser.add_argument("--password", default="admin123")
    parser.add_argument("--postgres", action="store_true")
    args = parser.parse_args()

    ContentStore().ensure_default_tenant()
    auth = bootstrap_user(args.email, args.password)
    print("Utilisateur créé:", auth["user_id"])
    print("Token (Bearer):", auth["access_token"][:40] + "...")

    if args.postgres:
        from storage.postgres_backend import apply_all_schemas

        files = apply_all_schemas()
        print("Postgres schemas:", files)

    print("\nProchaines étapes:")
    print("  python scripts/health_check.py")
    print("  uvicorn api.main:app --reload")
    return 0


if __name__ == "__main__":
    sys.exit(main())
