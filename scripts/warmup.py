"""
Warm-up automatique du quota email.

Lit EMAIL_WARMUP_START_DATE dans .env et calcule la semaine courante.
Met à jour EMAIL_DAILY_MAX selon le planning suivant :

  Semaine 1 :  5 emails/jour
  Semaine 2 : 10 emails/jour
  Semaine 3 : 20 emails/jour
  Semaine 4 : 30 emails/jour
  Semaine 5+ : 50 emails/jour

Usage :
  python scripts/warmup.py          → affiche le quota actuel
  python scripts/warmup.py --apply  → met à jour .env si le quota a changé
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"

# Planning semaine → quota
WARMUP_SCHEDULE: list[tuple[int, int]] = [
    (1, 5),
    (2, 10),
    (3, 20),
    (4, 30),
    (5, 50),
]


def _read_env(key: str) -> str:
    """Lit une variable depuis .env (sans charger pydantic)."""
    text = ENV_FILE.read_text(encoding="utf-8")
    m = re.search(rf"^{re.escape(key)}\s*=\s*(.+)$", text, re.MULTILINE)
    return m.group(1).strip() if m else ""


def _write_env(key: str, value: str) -> None:
    """Met à jour une variable dans .env."""
    text = ENV_FILE.read_text(encoding="utf-8")
    new_text = re.sub(
        rf"^({re.escape(key)}\s*=\s*)(.+)$",
        rf"\g<1>{value}",
        text,
        flags=re.MULTILINE,
    )
    ENV_FILE.write_text(new_text, encoding="utf-8")


def compute_quota() -> tuple[int, int, int]:
    """
    Retourne (semaine_courante, quota_actuel_dans_env, quota_cible).
    """
    start_raw = _read_env("EMAIL_WARMUP_START_DATE")
    if not start_raw:
        print("[warmup] EMAIL_WARMUP_START_DATE non défini dans .env — warm-up ignoré.")
        sys.exit(0)

    try:
        start = datetime.strptime(start_raw, "%Y-%m-%d").date()
    except ValueError:
        print(f"[warmup] Date invalide : {start_raw!r} (attendu YYYY-MM-DD)")
        sys.exit(1)

    today = date.today()
    days_elapsed = (today - start).days
    week = max(1, days_elapsed // 7 + 1)

    # Trouve le quota correspondant à la semaine courante
    target = WARMUP_SCHEDULE[-1][1]
    for w, quota in WARMUP_SCHEDULE:
        if week <= w:
            target = quota
            break

    current_raw = _read_env("EMAIL_DAILY_MAX")
    current = int(current_raw) if current_raw.isdigit() else 5

    return week, current, target


def main() -> None:
    parser = argparse.ArgumentParser(description="Warm-up email quota manager")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Met à jour EMAIL_DAILY_MAX dans .env si le quota a changé",
    )
    args = parser.parse_args()

    week, current, target = compute_quota()

    print(f"[warmup] Semaine {week} — quota actuel : {current}/jour — quota cible : {target}/jour")

    if args.apply:
        if current != target:
            _write_env("EMAIL_DAILY_MAX", str(target))
            print(f"[warmup] EMAIL_DAILY_MAX mis à jour : {current} → {target}")
        else:
            print("[warmup] Quota déjà à jour, aucune modification.")
    else:
        print("[warmup] Mode lecture seule. Utilise --apply pour mettre à jour .env")

    # Résumé du planning complet
    start_raw = _read_env("EMAIL_WARMUP_START_DATE")
    start = datetime.strptime(start_raw, "%Y-%m-%d").date()
    print("\nPlanning complet :")
    for w, q in WARMUP_SCHEDULE:
        day_start = (w - 1) * 7
        from datetime import timedelta
        d = start + timedelta(days=day_start)
        marker = " ← aujourd'hui" if w == week else ""
        print(f"  Semaine {w} (à partir du {d.strftime('%d/%m/%Y')}) : {q} emails/jour{marker}")
    last_w = WARMUP_SCHEDULE[-1][0]
    from datetime import timedelta
    d = start + timedelta(days=last_w * 7)
    marker = " ← aujourd'hui" if week > last_w else ""
    print(f"  Semaine {last_w + 1}+ (à partir du {d.strftime('%d/%m/%Y')}) : {WARMUP_SCHEDULE[-1][1]} emails/jour{marker}")


if __name__ == "__main__":
    main()
