"""Vérifie SCRAPER_WEB_GOOGLE_API_KEY + SCRAPER_WEB_GOOGLE_CX."""

from __future__ import annotations

import sys

import httpx

from config import settings


def main() -> int:
    key = (settings.scraper_web_google_api_key or "").strip()
    cx = (settings.scraper_web_google_cx or "").strip()
    if not key or not cx:
        print("Manque SCRAPER_WEB_GOOGLE_API_KEY ou SCRAPER_WEB_GOOGLE_CX dans .env", file=sys.stderr)
        return 1
    r = httpx.get(
        "https://www.googleapis.com/customsearch/v1",
        params={"key": key, "cx": cx, "q": "agence marketing", "num": 3},
        timeout=30,
    )
    data = r.json()
    if r.status_code != 200:
        err = data.get("error") or {}
        print(f"ERREUR {r.status_code}: {err.get('message', data)}", file=sys.stderr)
        if r.status_code == 403:
            msg_low = str(err.get("message", "")).lower()
            if "does not have the access" in msg_low or "custom search json" in msg_low:
                print(
                    "\n⚠ Depuis 2024, l'API Custom Search JSON n'est plus ouverte aux "
                    "NOUVEAUX comptes Google (même avec API activée + facturation).\n"
                    "Source : https://developers.google.com/custom-search/v1/overview\n\n"
                    "→ Utilisez dans .env : SCRAPER_WEB_SEARCH_PROVIDER=bing\n"
                    "   ou google_playwright (navigateur sur google.com).",
                    file=sys.stderr,
                )
            else:
                print(
                    "\nCorrection :\n"
                    "1. https://console.cloud.google.com/apis/library/customsearch.googleapis.com\n"
                    "   → Activer sur le projet de la clé\n"
                    "2. Facturation liée au projet\n"
                    "3. Attendre 2–5 min puis relancer.",
                    file=sys.stderr,
                )
        return 1
    items = data.get("items") or []
    print(f"OK — {len(items)} résultat(s) test")
    for item in items:
        print(f"  - {item.get('link', '')}")
    if not items:
        print(
            "API OK mais 0 résultat : sur programmablesearchengine.google.com "
            "activez « Rechercher sur tout le Web » pour ce moteur (CX).",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
