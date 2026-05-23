"""
Vérifie la session LinkedIn avant un scrape.

Usage:
  python scripts/check_linkedin_session.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraper.linkedin_stability import session_file_age_days, validate_linkedin_session_file


def main() -> int:
    try:
        path = validate_linkedin_session_file()
        age = session_file_age_days("linkedin")
        age_txt = f"{age:.1f} j" if age is not None else "?"
        print(f"OK — session LinkedIn : {path}")
        print(f"Âge : {age_txt}")
        print("Lancez le scraper : python -m scraper.cli run --app linkedin ...")
        return 0
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
