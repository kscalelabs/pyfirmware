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


class Logger:
    """Simple console logger with multiple levels."""
    
    def __init__(
        self, 
        logdir: str,
        console_level: LogLevel = LogLevel.INFO
    ):
        """
        Initialize logger.
        
        Args:
            logdir: Directory to store log files (unused, kept for compatibility)
            console_level: Minimum level for console output
        """
        self.logdir = logdir
        self.console_level = console_level

    def _should_log_to_console(self, level: LogLevel) -> bool:
        """Check if message should be logged to console."""
        return level.value >= self.console_level.value

    def log(self, level: LogLevel, message: str, extra_data: Optional[Dict[str, Any]] = None) -> None:
        """Log message to console with appropriate formatting."""
        if not self._should_log_to_console(level):
            return
            
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
        
        print(f"{color}[{timestamp}] {level.name:8} | {message}{extra_str}{reset_color}")

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


# Factory function for easy logger creation
def create_logger(
    logdir: str,
    console_level: str = "INFO"
) -> Logger:
    """
    Factory function to create a logger.
    
    Args:
        logdir: Directory to store log files (unused, kept for compatibility)
        console_level: Console log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    
    Returns:
        Logger instance
    """
    # Convert string level to LogLevel enum
    level_map = {
        "DEBUG": LogLevel.DEBUG,
        "INFO": LogLevel.INFO,
        "WARNING": LogLevel.WARNING,
        "ERROR": LogLevel.ERROR,
        "CRITICAL": LogLevel.CRITICAL
    }
    
    return Logger(
        logdir=logdir,
        console_level=level_map.get(console_level.upper(), LogLevel.INFO)
    )


if __name__ == "__main__":
    # Test the logger
    logger = create_logger("/tmp", console_level="DEBUG")
    
    logger.info("Test info message")
    logger.warning("Test warning message", extra_data={"test": True})
    logger.error("Test error message")
    
    print("Logger test completed")