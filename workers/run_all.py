"""Workers acquisition + content + outbox — un processus."""

from __future__ import annotations

import threading
import time

from utils import browser_pool
from workers.content_runner import ContentJobQueue
from workers.content_jobs import execute_content_job
from workers.queue import JobQueue
from workers.runner import _execute
from workers.worker_runtime import install_signal_handlers, request_shutdown, run_loop


def _outbox_thread() -> None:
    from workers.outbox_relay import relay_once

    while True:
        try:
            relay_once()
        except Exception:
            pass
        time.sleep(5.0)


def _combined_loop() -> None:
    """Mode legacy — alterne acquisition/content (sans double run_loop)."""
    acq = JobQueue()
    content = ContentJobQueue()
    from workers.runner import run_once as acquisition_once
    from workers.content_runner import run_once as content_once

    install_signal_handlers()
    threading.Thread(target=_outbox_thread, daemon=True).start()
    print("Workers combinés (acquisition + content). Ctrl+C pour arrêter.")
    from workers.worker_runtime import _shutdown

    while not _shutdown.is_set():
        acquisition_once()
        content_once()
        time.sleep(1.5)
    browser_pool.shutdown()


def main() -> None:
    import sys

    if "--combined" in sys.argv:
        _combined_loop()
        return
    threading.Thread(target=_outbox_thread, daemon=True).start()
    acq = JobQueue()
    content = ContentJobQueue()

    def _acq_loop():
        run_loop(acq, _execute, worker_id="acquisition-combined")

    def _content_loop():
        run_loop(content, execute_content_job, worker_id="content-combined")

    t1 = threading.Thread(target=_acq_loop, daemon=True)
    t2 = threading.Thread(target=_content_loop, daemon=True)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    browser_pool.shutdown()


if __name__ == "__main__":
    main()
