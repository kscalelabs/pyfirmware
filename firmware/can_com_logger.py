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
        
        # Single log file for all CAN buses
        self.log_file_path = os.path.join(self.run_dir, "can_communication.log")
        self.log_file = open(self.log_file_path, "w", encoding="utf-8")
        
        # Write header
        self.log_file.write(f"# CAN Communication Log - Run {self.timestamp}\n")
        self.log_file.write("# Format: [timestamp] SENDER: MESSAGE\n")
        self.log_file.write("#" + "="*80 + "\n\n")
        self.log_file.flush()
        
        print(f"✓ CAN communication logger initialized: {self.run_dir}")
        print(f"✓ Logger will save ALL CAN logs to: {os.path.abspath(self.log_file_path)}")
    
    def log(self, sender: str, message: str) -> None:
        """Log a message with timestamp and sender."""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]  # Include milliseconds
        self.log_file.write(f"[{timestamp}] {sender}: {message}\n")
        self.log_file.flush()
    
    def close(self) -> None:
        """Close the log file."""
        try:
            self.log_file.write(f"\n# Log session ended at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            self.log_file.close()
            print(f"✓ CAN communication logger closed: {self.run_dir}")
        except Exception as e:
            print(f"Error closing CAN log file: {e}")


class DummyCanComLogger:
    """Dummy logger that does nothing when logging is disabled."""
    
    def log(self, sender: str, message: str) -> None:
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