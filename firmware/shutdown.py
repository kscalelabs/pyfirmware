"""Centralized shutdown manager for reliable cleanup.

This module provides a singleton ShutdownManager that ensures all resources
are cleaned up properly, whether the program exits normally, crashes, or is
interrupted with Ctrl+C.
"""

import atexit
import os
import signal
import threading
from typing import Callable, List, Optional


class ShutdownManager:
    """Centralized shutdown manager that ensures proper cleanup.

    This class:
    - Registers signal handlers for SIGINT and SIGTERM
    - Uses atexit to ensure cleanup happens even on crashes
    - Maintains an ordered list of cleanup callbacks
    - Ensures cleanup only happens once
    - Handles exceptions during cleanup gracefully
    """

    _instance: Optional["ShutdownManager"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "ShutdownManager":
        """Ensure only one ShutdownManager instance exists (singleton pattern)."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Initialize the shutdown manager."""
        if self._initialized:
            return

        self._initialized = True
        self._cleanup_callbacks: List[tuple[str, Callable[[], None]]] = []
        self._shutdown_done = False

        # Register atexit handler (catches crashes and normal exits)
        atexit.register(self._execute_shutdown)

        # Register signal handlers (catches Ctrl+C and kill signals)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def register_cleanup(self, name: str, callback: Callable[[], None]) -> None:
        """Register a cleanup callback to be called during shutdown.

        Callbacks are executed in reverse order of registration (LIFO).
        This ensures that resources are cleaned up in the opposite order
        they were created.

        Args:
            name: Descriptive name for the cleanup callback (for logging)
            callback: Function to call during shutdown (should not raise exceptions)
        """
        with self._lock:
            self._cleanup_callbacks.append((name, callback))
            print(f"🔧 Registered cleanup: {name}")

    def _signal_handler(self, signum: int, frame: object) -> None:
        """Handle shutdown signals (SIGINT, SIGTERM)."""
        self._execute_shutdown()
        os._exit(0)

    def _execute_shutdown(self) -> None:
        """Execute all registered cleanup callbacks in reverse order."""
        # Simple atomic check: only run once
        with self._lock:
            if self._shutdown_done:
                return
            self._shutdown_done = True

        print("\n🛑 Shutting down...")

        # Execute callbacks in reverse order (LIFO)
        for name, callback in reversed(self._cleanup_callbacks):
            try:
                print(f"  ↳ {name}")
                callback()
            except Exception as e:
                print(f"  ❌ Error in {name}: {e}")

        print("✅ Shutdown complete\n")

    def is_shutting_down(self) -> bool:
        """Check if shutdown is in progress."""
        with self._lock:
            return self._shutdown_done


# Global singleton instance
_shutdown_manager: Optional[ShutdownManager] = None


def get_shutdown_manager() -> ShutdownManager:
    """Get the global ShutdownManager instance."""
    global _shutdown_manager
    if _shutdown_manager is None:
        _shutdown_manager = ShutdownManager()
    return _shutdown_manager
