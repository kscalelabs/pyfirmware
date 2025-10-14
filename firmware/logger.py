"""Simple console logger with multiple levels and file writing capability."""

import atexit
import json
import os
import queue
import threading
import time
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class LogLevel(Enum):
    """Log levels with numeric values for comparison."""
    WRITE = 5      # Lowest level - file only, never console
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50
    USER_ACTION = 60


class Logger:
    """Simple console logger with multiple levels."""
    
    def __init__(
        self, 
        logdir: str,
        console_level = LogLevel.INFO
    ):
        """
        Initialize logger.
        
        Args:
            console_level: Minimum level for console output (LogLevel enum or string)
            logdir: Directory for file logging (if None, file logging is disabled)
        """
        # Handle string inputs by converting to LogLevel enum
        if isinstance(console_level, str):
            self.console_level = LogLevel[console_level.upper()]
        else:
            self.console_level = console_level
        self.last_message = None
        self.repeat_count = 0
        
        # Initialize file logging if logdir is provided
        self.logdir = logdir
        self.file_logging_enabled = logdir is not None
        if self.file_logging_enabled:
            self.logpath = os.path.join(logdir, "kinfer_log.ndjson")
            self.running = True
            self.queue = queue.Queue()
            self.thread = threading.Thread(target=self._log_worker, args=(self.queue, self.logpath), daemon=True)
            self.thread.start()
            self._register_shutdown_handlers()

    def _register_shutdown_handlers(self) -> None:
        """Register shutdown handlers for graceful file logging cleanup."""
        def _safe_shutdown() -> None:
            try:
                self._shutdown()
            except Exception:
                pass

        atexit.register(_safe_shutdown)

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
        """Shutdown the file logging worker thread."""
        if self.file_logging_enabled:
            self.running = False
            self.queue.join()
            self.thread.join()

    def _should_log_to_console(self, level: LogLevel) -> bool:
        """Check if message should be logged to console."""
        # WRITE level should never appear in console
        if level == LogLevel.WRITE:
            return False
        return level.value >= self.console_level.value

    def log(self, level: LogLevel, message: str, extra_data: Optional[Dict[str, Any]] = None) -> None:
        """Log message to console with appropriate formatting."""
        # Special handling for WRITE level - only write to file, no console output
        if level == LogLevel.WRITE:
            if self.file_logging_enabled:
                log_entry = {
                    "timestamp": time.time(),
                    "datetime": datetime.now().isoformat(),
                    "level": level.name,
                    "message": message,
                    "extra": extra_data or {}
                }
                self.queue.put(log_entry)
            return
        
        if not self._should_log_to_console(level):
            return
        
        # Special handling for USER_ACTION level
        if level == LogLevel.USER_ACTION:
            print("----------")
            print(message)  # Plain white text, no timestamp or level
            self.last_message = None  # Reset deduplication for user actions
            self.repeat_count = 0
            return
        
        # Create message key for deduplication (exclude timestamp)
        message_key = f"{level.name}|{message}"
        if extra_data:
            message_key += f"|{json.dumps(extra_data, separators=(',', ':'))}"
        
        # Check for message deduplication
        if message_key == self.last_message:
            self.repeat_count += 1
            # Update the previous line with repeat count
            print(f"\033[F\033[K", end="")  # Move up one line and clear it
            if self.repeat_count == 1:
                repeat_str = " x2"
            else:
                repeat_str = f" x{self.repeat_count + 1}"
            print(f"{self._format_message(level, message, extra_data)}{repeat_str}")
            return
        else:
            print(self._format_message(level, message, extra_data))
            self.last_message = message_key
            self.repeat_count = 0

    def _format_message(self, level: LogLevel, message: str, extra_data: Optional[Dict[str, Any]] = None) -> str:
        """Format a log message with colors and timestamp."""
        # Color coding for console output
        colors = {
            LogLevel.DEBUG: "\033[36m",      # Cyan
            LogLevel.INFO: "\033[32m",       # Green
            LogLevel.WARNING: "\033[33m",    # Yellow
            LogLevel.ERROR: "\033[31m",      # Red
            LogLevel.CRITICAL: "\033[35m"    # Magenta
        }
        reset_color = "\033[0m"
        
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        color = colors.get(level, "")
        
        # Format extra data if present
        extra_str = ""
        if extra_data:
            extra_str = f" | {json.dumps(extra_data, separators=(',', ':'))}"
        
        return f"{color}[{timestamp}] {level.name:8} | {message}{extra_str}{reset_color}"

    # Convenience methods for different log levels
    def debug(self, message: str, extra_data: Optional[Dict[str, Any]] = None) -> None:
        """Log debug message."""
        self.log(LogLevel.DEBUG, message, extra_data)

    def info(self, message: str, extra_data: Optional[Dict[str, Any]] = None) -> None:
        """Log info message."""
        self.log(LogLevel.INFO, message, extra_data)

    def warning(self, message: str, extra_data: Optional[Dict[str, Any]] = None) -> None:
        """Log warning message."""
        self.log(LogLevel.WARNING, message, extra_data)

    def error(self, message: str, extra_data: Optional[Dict[str, Any]] = None) -> None:
        """Log error message."""
        self.log(LogLevel.ERROR, message, extra_data)

    def critical(self, message: str, extra_data: Optional[Dict[str, Any]] = None) -> None:
        """Log critical message."""
        self.log(LogLevel.CRITICAL, message, extra_data)

    def user_action(self, message: str) -> None:
        """Log user action message with separator line."""
        self.log(LogLevel.USER_ACTION, message)

    def write(self, timestamp: float, data: Dict[str, Any]) -> None:
        """Write structured data to file (compatible with original logger.py interface)."""
        if self.file_logging_enabled:
            log_entry = {"timestamp": timestamp, **data}
            self.queue.put(log_entry)
