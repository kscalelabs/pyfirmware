"""Asynchronous structured NDJSON logger with background flushing."""

import atexit
import json
import queue
import threading
from typing import Any, Dict


class Logger:
    def __init__(self, logpath: str) -> None:
        self.logpath = logpath

        # Start background threads for processing logs
        self._register_shutdown_handlers()
        self.running = True
        self.queue = queue.Queue()
        self.thread = threading.Thread(target=self._log_worker, args=(self.queue, self.logpath), daemon=True)
        self.thread.start()

    def _register_shutdown_handlers(self) -> None:
        def _safe_shutdown() -> None:
            try:
                self._shutdown()
            except Exception:
                pass

        atexit.register(_safe_shutdown)

    def _log_worker(self, q: queue.Queue, filepath: str) -> None:
        """Background worker that processes logs from the queue in batches."""
        print("Logging worker started")
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
        self.running = False
        self.queue.join()
        self.thread.join()

    def log(self, timestamp: float, data: Dict[str, Any]) -> None:
        self.queue.put({"timestamp": timestamp, **data})


if __name__ == "__main__":
    import time

    logger = Logger("logger_test")
    logger.log(time.time(), {"test": "1"})
    time.sleep(1)
    logger.log(time.time(), {"test": "2"})
