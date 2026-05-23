"""Vérifie sessions/instagram.json (âge, taille)."""

from __future__ import annotations

import sys

from scraper.instagram_stability import session_file_age_days, validate_instagram_session_file


def main() -> int:
    try:
        path = validate_instagram_session_file()
        age = session_file_age_days("instagram")
        if age is not None:
            print(f"OK — {path} (âge {age:.1f} j)")
        else:
            print(f"OK — {path}")
        return 0
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
