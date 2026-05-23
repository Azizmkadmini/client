from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from filelock import FileLock


@contextmanager
def locked_path(path: Path, timeout: int = 30) -> Iterator[None]:
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock = FileLock(str(lock_path), timeout=timeout)
    with lock:
        yield
