"""Canaux de session navigateur : scrape vs outreach (LinkedIn séparé)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from config import settings

LinkedInRole = Literal["scrape", "outreach"]

LINKEDIN_SCRAPE = "linkedin-scrape"
LINKEDIN_OUTREACH = "linkedin-outreach"
LINKEDIN_PUBLISH = "linkedin-publish"
LINKEDIN_LEGACY = "linkedin"

LOGIN_CHANNEL_CHOICES = (
    "linkedin",
    LINKEDIN_SCRAPE,
    LINKEDIN_OUTREACH,
    "instagram",
    "whatsapp",
)


def scrape_session_channel(logical: str) -> str:
    if logical.strip().lower() == "linkedin":
        return LINKEDIN_SCRAPE
    return logical.strip().lower()


def outreach_session_channel(logical: str) -> str:
    if logical.strip().lower() == "linkedin":
        return LINKEDIN_OUTREACH
    return logical.strip().lower()


def linkedin_session_candidates(role: LinkedInRole) -> list[str]:
    if role == "scrape":
        return [LINKEDIN_SCRAPE, LINKEDIN_LEGACY]
    return [LINKEDIN_OUTREACH, LINKEDIN_LEGACY]


def session_file_path(channel: str) -> Path:
    return settings.path(settings.session_dir) / f"{channel}.json"


def first_existing_session(channel: str, *, role: LinkedInRole | None = None) -> Path | None:
    if channel in (LINKEDIN_LEGACY, LINKEDIN_SCRAPE, LINKEDIN_OUTREACH) or (
        role is not None
    ):
        role = role or (
            "scrape" if channel in (LINKEDIN_SCRAPE, LINKEDIN_LEGACY) else "outreach"
        )
        if channel == LINKEDIN_LEGACY:
            role = "scrape"
        for name in linkedin_session_candidates(role):
            path = session_file_path(name)
            if path.is_file():
                return path
        return None
    path = session_file_path(channel)
    return path if path.is_file() else None


def normalize_login_channel(channel: str) -> tuple[str, str]:
    """
    Retourne (fichier de stockage, clé URLs landing/feed).
    """
    raw = channel.strip().lower()
    if raw == LINKEDIN_SCRAPE:
        return LINKEDIN_SCRAPE, LINKEDIN_LEGACY
    if raw == LINKEDIN_OUTREACH:
        return LINKEDIN_OUTREACH, LINKEDIN_LEGACY
    if raw == LINKEDIN_PUBLISH:
        return LINKEDIN_PUBLISH, LINKEDIN_LEGACY
    if raw == LINKEDIN_LEGACY:
        return LINKEDIN_LEGACY, LINKEDIN_LEGACY
    return raw, raw


def login_storage_targets(channel: str) -> list[str]:
    """Fichiers JSON écrits lors d'un ``outreach.py login``."""
    storage, _ = normalize_login_channel(channel)
    if storage == LINKEDIN_LEGACY:
        return [LINKEDIN_LEGACY, LINKEDIN_SCRAPE, LINKEDIN_OUTREACH]
    return [storage]


def resolve_storage_path(channel: str) -> Path:
    """Chemin du fichier storage_state à charger (avec repli legacy)."""
    if channel == LINKEDIN_SCRAPE:
        found = first_existing_session("linkedin", role="scrape")
        return found if found else session_file_path(LINKEDIN_SCRAPE)
    if channel == LINKEDIN_OUTREACH:
        found = first_existing_session("linkedin", role="outreach")
        return found if found else session_file_path(LINKEDIN_OUTREACH)
    if channel == LINKEDIN_PUBLISH:
        path = session_file_path(LINKEDIN_PUBLISH)
        return path if path.is_file() else session_file_path(LINKEDIN_LEGACY)
    if channel == LINKEDIN_LEGACY:
        found = first_existing_session("linkedin", role="scrape")
        return found if found else session_file_path(LINKEDIN_LEGACY)
    return session_file_path(channel)
