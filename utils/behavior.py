from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Optional

from config import settings


class HumanBehavior:
    def __init__(self) -> None:
        self.action_count = 0
        self._next_pause_at = random.randint(
            settings.pause_every_min,
            settings.pause_every_max,
        )

    def random_delay(self) -> None:
        time.sleep(random.uniform(settings.delay_min, settings.delay_max))

    def maybe_long_pause(self) -> None:
        self.action_count += 1
        if self.action_count >= self._next_pause_at:
            time.sleep(random.uniform(settings.long_pause_min, settings.long_pause_max))
            self.action_count = 0
            self._next_pause_at = random.randint(
                settings.pause_every_min,
                settings.pause_every_max,
            )

    def scroll_page(self, page, passes: Optional[int] = None) -> None:
        passes = passes or random.randint(2, 5)
        for _ in range(passes):
            delta = random.randint(250, 900)
            page.mouse.wheel(0, delta)
            time.sleep(random.uniform(0.4, 1.2))


class RateLimiter:
    """Façade — délègue au moteur central Phase 4."""

    def __init__(self, channel: str, daily_max: int, state_dir: Optional[Path] = None) -> None:
        from services.rate_limit_engine import CentralRateLimiter

        self._engine = CentralRateLimiter(channel, daily_max=daily_max, state_dir=state_dir)
        self.channel = channel
        self.daily_max = daily_max

    def remaining(self) -> int:
        return self._engine.remaining()

    def can_send(self) -> bool:
        return self._engine.can_send()

    def record_send(self) -> None:
        self._engine.record_send()
