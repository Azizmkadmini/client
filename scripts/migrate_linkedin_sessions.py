"""Copie sessions/linkedin.json vers linkedin-scrape et linkedin-outreach si absents."""

from __future__ import annotations

import shutil
import sys

from config import settings
from utils.session_channels import (
    LINKEDIN_LEGACY,
    LINKEDIN_OUTREACH,
    LINKEDIN_SCRAPE,
    session_file_path,
)


def main() -> int:
    legacy = session_file_path(LINKEDIN_LEGACY)
    if not legacy.is_file():
        print(f"Rien à migrer : {legacy} introuvable.")
        return 1
    created = 0
    for name in (LINKEDIN_SCRAPE, LINKEDIN_OUTREACH):
        dest = session_file_path(name)
        if dest.is_file():
            print(f"Déjà présent : {dest.name}")
            continue
        shutil.copy2(legacy, dest)
        print(f"Copié → {dest}")
        created += 1
    if created:
        print(
            "\nRecommandé : reconnectez des comptes distincts avec :\n"
            "  python outreach.py login linkedin-scrape\n"
            "  python outreach.py login linkedin-outreach"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
