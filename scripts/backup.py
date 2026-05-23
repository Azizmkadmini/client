from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from config import settings


def backup(target_dir: Path | None = None) -> Path:
    destination = target_dir or settings.path("backups") / datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    destination.mkdir(parents=True, exist_ok=True)
    for relative in (
        settings.leads_csv,
        settings.app_db_path,
        settings.connector_sqlite_path,
        settings.connector_queue_path,
        settings.opt_out_csv,
        settings.log_dir,
    ):
        source = settings.path(relative)
        if source.is_dir():
            shutil.copytree(source, destination / source.name, dirs_exist_ok=True)
        elif source.exists():
            target = destination / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    return destination


if __name__ == "__main__":
    path = backup()
    print(f"Backup created at {path}")
