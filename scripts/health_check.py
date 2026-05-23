"""
Vérifications pré-run — sessions, SMTP, Redis, config scraper.

Usage:
  python scripts/health_check.py
  python scripts/health_check.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.platform_health import run_checks


def main() -> int:
    parser = argparse.ArgumentParser(description="Health check plateforme outreach")
    parser.add_argument("--json", action="store_true", help="Sortie JSON")
    args = parser.parse_args()
    report = run_checks()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("=== Health check ===\n")
        for name, data in report.items():
            if name == "ok":
                continue
            if not isinstance(data, dict):
                continue
            status = "OK" if data.get("ok") else ("SKIP" if data.get("skipped") else "FAIL")
            print(f"  [{status}] {name}")
            if data.get("error"):
                print(f"         {data['error']}")
            elif data.get("path"):
                print(f"         {data['path']}")
        print(f"\nGlobal: {'OK' if report['ok'] else 'ÉCHEC — corrigez les FAIL avant un run long'}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
