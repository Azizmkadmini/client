from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from config import settings


class ConnectorLogger:
    def __init__(self, log_dir: Optional[Path] = None) -> None:
        self.log_dir = Path(log_dir or settings.path(settings.log_dir))
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.processed_path = settings.path(settings.connector_processed_log)
        self.rejected_path = self.log_dir / "connector_rejected.jsonl"
        self.error_path = self.log_dir / "connector_errors.jsonl"

    def log_processed(self, record: dict[str, Any]) -> None:
        self._append(self.processed_path, record)

    def log_rejected(self, record: dict[str, Any]) -> None:
        self._append(self.rejected_path, record)

    def log_error(self, record: dict[str, Any]) -> None:
        self._append(self.error_path, record)

    def _append(self, path: Path, record: dict[str, Any]) -> None:
        payload = dict(record)
        payload.setdefault("timestamp", datetime.utcnow().isoformat())
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def summary(self) -> dict[str, int]:
        return {
            "processed": self._count_lines(self.processed_path),
            "rejected": self._count_lines(self.rejected_path),
            "errors": self._count_lines(self.error_path),
        }

    def _count_lines(self, path: Path) -> int:
        if not path.exists():
            return 0
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
