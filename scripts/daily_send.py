"""
Runner quotidien — à lancer chaque matin en semaine.

Enchaîne automatiquement :
  1. Vérification jour (bloque le weekend)
  2. Mise à jour du quota warm-up (--apply)
  3. Envoi des emails en attente (scraper send)
  4. Résumé dans les logs

Usage :
  python scripts/daily_send.py             → exécution normale
  python scripts/daily_send.py --force     → ignore la vérification weekend
  python scripts/daily_send.py --dry-run   → simule sans envoyer

Automatisation Windows (Planificateur de tâches) :
  Programme  : python
  Arguments  : C:\\client\\scripts\\daily_send.py
  Démarrer dans : C:\\client
  Déclencheur  : Tous les jours à 09:00 (lun-ven)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_FILE = ROOT / "logs" / "daily_send.jsonl"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


def _log(event: str, data: dict) -> None:
    record = {"ts": datetime.now().isoformat(), "event": event, **data}
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"[daily_send] {event}: {data}")


def _run(cmd: list[str]) -> tuple[int, str]:
    """Lance une commande et retourne (code_retour, sortie)."""
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    output = (result.stdout + result.stderr).strip()
    return result.returncode, output


def main() -> None:
    parser = argparse.ArgumentParser(description="Runner quotidien d'envoi email")
    parser.add_argument("--force",   action="store_true", help="Ignore la vérification weekend")
    parser.add_argument("--dry-run", action="store_true", help="Simule sans envoyer")
    args = parser.parse_args()

    now = datetime.now()
    weekday = now.weekday()  # 0=lundi … 6=dimanche

    _log("start", {"date": now.strftime("%Y-%m-%d %H:%M"), "weekday": now.strftime("%A")})

    # ── Étape 1 : Vérification weekend ──────────────────────────────────────────
    if weekday >= 5 and not args.force:
        _log("skip", {"reason": "weekend", "day": now.strftime("%A")})
        print("[daily_send] Weekend détecté — envoi annulé. Utilise --force pour forcer.")
        sys.exit(0)

    # ── Étape 2 : Mise à jour quota warm-up ─────────────────────────────────────
    print("[daily_send] Vérification quota warm-up...")
    code, out = _run([sys.executable, "scripts/warmup.py", "--apply"])
    _log("warmup", {"output": out, "code": code})
    if code != 0:
        _log("error", {"step": "warmup", "output": out})
        sys.exit(1)

    # ── Étape 3 : Envoi emails ───────────────────────────────────────────────────
    if args.dry_run:
        print("[daily_send] --dry-run activé, envoi simulé.")
        _log("dry_run", {"message": "Envoi simulé, aucun email envoyé."})
        sys.exit(0)

    print("[daily_send] Lancement de l'envoi email...")
    code, out = _run([sys.executable, "-m", "scraper.cli", "send"])
    _log("send", {"output": out, "code": code})

    if code != 0:
        _log("error", {"step": "send", "output": out})
        print(f"[daily_send] ERREUR lors de l'envoi :\n{out}")
        sys.exit(1)

    # ── Étape 4 : Résumé ─────────────────────────────────────────────────────────
    # Lit le nombre d'emails envoyés depuis la sortie
    sent = 0
    for line in out.splitlines():
        if "Emails envoyés" in line or "envoy" in line.lower():
            import re
            m = re.search(r"(\d+)", line)
            if m:
                sent = int(m.group(1))
                break

    _log("done", {"emails_sent": sent, "output_preview": out[:300]})
    print(f"[daily_send] Terminé — {sent} email(s) envoyé(s).")


if __name__ == "__main__":
    main()
