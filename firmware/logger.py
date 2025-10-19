"""Asynchronous structured NDJSON logger with background flushing."""

import json
import os
import queue
import threading
from typing import Any, Dict

from firmware.shutdown import get_shutdown_manager


class Logger:
    def __init__(self, logdir: str) -> None:
        self.logpath = os.path.join(logdir, "kinfer_log.ndjson")

        # Start background threads for processing logs
        self.running = True
        self.queue: queue.Queue[Dict[str, Any]] = queue.Queue()
        self.thread = threading.Thread(target=self._log_worker, args=(self.queue, self.logpath), daemon=True)
        self.thread.start()

        # Register cleanup with shutdown manager
        shutdown_mgr = get_shutdown_manager()
        shutdown_mgr.register_cleanup("Logger", self._shutdown)

    def _log_worker(self, q: queue.Queue, filepath: str) -> None:
        """Background worker that processes logs from the queue in batches."""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "a") as f:
            batch = []
            while self.running or not q.empty():
                try:
                    while True:
                        batch.append(q.get_nowait())
                        q.task_done()
                except queue.Empty:
                    if batch:
                        f.write("".join(json.dumps(entry) + "\n" for entry in batch))
                        f.flush()
                        batch = []
                    threading.Event().wait(1.0)

    def _shutdown(self) -> None:
        """Shutdown the logger thread and flush remaining logs."""
        if not self.running:
            return  # Already shut down
        self.running = False
        self.queue.join()
        self.thread.join(timeout=2.0)

    def log(self, timestamp: float, data: Dict[str, Any]) -> None:
        self.queue.put({"timestamp": timestamp, **data})


if __name__ == "__main__":
    import time

    logger = Logger("logger_test")
    logger.log(time.time(), {"test": "1"})
    time.sleep(1)
    logger.log(time.time(), {"test": "2"})
