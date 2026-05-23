from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass

from config import settings

logger = logging.getLogger(__name__)


@dataclass
class ScraperResult:
    ran: bool = False
    output_exists: bool = False
    error: str = ""


def run_scraper() -> ScraperResult:
    paths = [settings.path(settings.scraper_output_csv)]
    ig = (getattr(settings, "scraper_instagram_output_csv", None) or "").strip()
    if ig:
        paths.append(settings.path(ig))
    output_exists = any(p.exists() for p in paths)
    result = ScraperResult(output_exists=output_exists)

    command = settings.scraper_command.strip()
    if not command:
        if not result.output_exists:
            logger.warning("scraper output missing (checked: %s)", paths)
        return result

    try:
        subprocess.run(command, shell=True, check=True, cwd=str(settings.project_root))
        result.ran = True
        result.output_exists = any(p.exists() for p in paths)
    except subprocess.CalledProcessError as exc:
        result.error = f"scraper command failed with exit code {exc.returncode}"
        logger.error(result.error)
    return result
