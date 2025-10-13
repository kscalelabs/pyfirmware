"""Simple console logger with multiple levels."""

import json
import time
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class LogLevel(Enum):
    """Log levels with numeric values for comparison."""
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
        console_level = LogLevel.INFO
    ):
        """
        Initialize logger.
        
        Args:
            console_level: Minimum level for console output (LogLevel enum or string)
        """
        # Handle string inputs by converting to LogLevel enum
        if isinstance(console_level, str):
            self.console_level = LogLevel[console_level.upper()]
        else:
            self.console_level = console_level
        self.last_message = None
        self.repeat_count = 0

    def _should_log_to_console(self, level: LogLevel) -> bool:
        """Check if message should be logged to console."""
        return level.value >= self.console_level.value

    def log(self, level: LogLevel, message: str, extra_data: Optional[Dict[str, Any]] = None) -> None:
        """Log message to console with appropriate formatting."""
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
            # New message - reset repeat count
            if self.repeat_count > 0:
                # Clear any previous repeat indicators
                print(f"\033[F\033[K", end="")  # Move up one line and clear it
                print(self._format_message(level, message, extra_data))
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
