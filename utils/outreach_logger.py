"""Outreach event logging (sent / failed / replies) — JSONL under log_dir."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from config import settings


class OutreachLogger:
    def __init__(self, log_dir: Optional[Path] = None) -> None:
        self.log_dir = Path(log_dir or settings.path(settings.log_dir))
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.sent_path = self.log_dir / "sent.jsonl"
        self.failed_path = self.log_dir / "failed.jsonl"
        self.replies_path = self.log_dir / "replies.jsonl"

    def log_sent(
        self,
        lead_id: str,
        channel: str,
        stage: str,
        message: str,
        *,
        subject: str = "",
    ) -> None:
        self._append(
            self.sent_path,
            {
                "lead_id": lead_id,
                "channel": channel,
                "stage": stage,
                "subject": subject,
                "message": message[:500],
            },
        )

    def log_failed(self, lead_id: str, channel: str, error: str) -> None:
        self._append(
            self.failed_path,
            {"lead_id": lead_id, "channel": channel, "error": error},
        )

    def log_reply(self, lead_id: str, *, channel: str = "manual", snippet: str = "") -> None:
        self._append(
            self.replies_path,
            {"lead_id": lead_id, "channel": channel, "snippet": snippet[:500]},
        )

    def _append(self, path: Path, record: dict[str, Any]) -> None:
        payload = dict(record)
        payload.setdefault("timestamp", datetime.utcnow().isoformat())
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _count_lines(self, path: Path) -> int:
        if not path.exists():
            return 0
        with path.open(encoding="utf-8") as handle:
            return sum(1 for line in handle if line.strip())

    def metrics(self) -> dict[str, Any]:
        sent = self._count_lines(self.sent_path)
        failed = self._count_lines(self.failed_path)
        replies = self._count_lines(self.replies_path)
        total = sent + failed
        success_rate = round(100.0 * sent / total, 1) if total else 0.0
        return {
            "sent": sent,
            "failed": failed,
            "replies": replies,
            "success_rate": success_rate,
        }
