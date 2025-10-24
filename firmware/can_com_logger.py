"""Simplified CAN communication logger."""

import os
from datetime import datetime
from typing import Any, Dict


class CanComLogger:
    """Simple logger for CAN communication messages."""
    
    def __init__(self, base_log_dir: str = "logs") -> None:
        """Initialize the CAN communication logger.
        
        Args:
            base_log_dir: Base directory for log files
        """
        self.base_log_dir = base_log_dir
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.run_dir = os.path.join(base_log_dir, f"run_{self.timestamp}")
        
        # Create the run directory
        os.makedirs(self.run_dir, exist_ok=True)
        
        # Track open file handles for each CAN bus
        self.can_files: Dict[int, Any] = {}
        
        print(f"✓ CAN communication logger initialized: {self.run_dir}")
        print(f"✓ Logger will save CAN logs to: {os.path.abspath(self.run_dir)}")
    
    def _get_can_file(self, can_index: int) -> Any:
        """Get or create file handle for a specific CAN bus."""
        if can_index not in self.can_files:
            log_file_path = os.path.join(self.run_dir, f"can{can_index}.log")
            self.can_files[can_index] = open(log_file_path, "w", encoding="utf-8")
            # Write header
            self.can_files[can_index].write(f"# CAN{can_index} Communication Log - Run {self.timestamp}\n")
            self.can_files[can_index].write("# Format: [timestamp] SENDER: MESSAGE\n")
            self.can_files[can_index].write("#" + "="*80 + "\n\n")
            self.can_files[can_index].flush()
        
        return self.can_files[can_index]
    
    def log(self, sender: str, message: str, can_index: int = 0) -> None:
        """Log a message with timestamp and sender."""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]  # Include milliseconds
        log_file = self._get_can_file(can_index)
        log_file.write(f"[{timestamp}] {sender}: {message}\n")
        log_file.flush()
    
    def close(self) -> None:
        """Close all log files."""
        for can_index, log_file in self.can_files.items():
            try:
                log_file.write(f"\n# Log session ended at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                log_file.close()
                print(f"✓ Closed CAN{can_index} log file")
            except Exception as e:
                print(f"Error closing CAN{can_index} log file: {e}")
        
        self.can_files.clear()
        print(f"✓ CAN communication logger closed: {self.run_dir}")


class DummyCanComLogger:
    """Dummy logger that does nothing when logging is disabled."""
    
    def log(self, sender: str, message: str, can_index: int = 0) -> None:
        pass
    
    def close(self) -> None:
        pass


if __name__ == "__main__":
    # Test the logger
    logger = CanComLogger()
    
    # Simulate some CAN messages
    logger.log("host", "TX: PING to actuator 10")
    logger.log("act_10", "RX: PING response")
    logger.log("host", "TX: CONTROL to actuator 10 - angle=1.234 rad, scaling=0.5")
    logger.log("act_10", "RX: FEEDBACK - angle=1.234 rad, velocity=0.567 rad/s, torque=2.345 Nm, temp=45.6°C")
    
    logger.close()