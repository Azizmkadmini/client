"""
Configuration initiale du projet (venv, deps, playwright, dossiers).

Usage:
  python scripts/setup_project.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, cwd=str(ROOT), check=True)


def main() -> None:
    venv_py = ROOT / ".venv" / "Scripts" / "python.exe"
    py = str(venv_py) if venv_py.exists() else sys.executable
    _run([py, "-m", "pip", "install", "-r", "requirements.txt"])
    dev = ROOT / "requirements-dev.txt"
    if dev.exists():
        _run([py, "-m", "pip", "install", "-r", str(dev)])
    _run([py, "-m", "playwright", "install", "chromium"])
    for folder in ("data", "logs", "leads", "sessions", "bot"):
        (ROOT / folder).mkdir(parents=True, exist_ok=True)
    env_example = ROOT / ".env.example"
    env_file = ROOT / ".env"
    if env_example.exists() and not env_file.exists():
        env_file.write_text(env_example.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Créé {env_file} depuis .env.example")
    print("\nProchaines étapes:")
    print("  1. Éditer .env (SMTP, clés API)")
    print("  2. python outreach.py login linkedin-scrape")
    print("  3. python scripts/health_check.py")
    print("  4. streamlit run dashboard.py")


if __name__ == "__main__":
    main()
