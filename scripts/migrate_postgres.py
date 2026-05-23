"""Applique les schémas PostgreSQL (acquisition + content)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from storage.postgres_backend import apply_all_schemas


def main() -> int:
    applied = apply_all_schemas()
    print("Appliqué:", applied)
    return 0


if __name__ == "__main__":
    sys.exit(main())
