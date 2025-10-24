"""CAN communication logger for debugging and analysis."""

import os
import time
from datetime import datetime
from typing import Any, Dict, Optional

from firmware.actuators import Mux


class CanComLogger:
    """Logger for CAN communication messages with separate files per CAN bus."""
    
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
    
    def _get_can_file(self, can_index: int) -> Any:
        """Get or create file handle for a specific CAN bus."""
        if can_index not in self.can_files:
            log_file_path = os.path.join(self.run_dir, f"can{can_index}.log")
            self.can_files[can_index] = open(log_file_path, "w", encoding="utf-8")
            # Write header
            self.can_files[can_index].write(f"# CAN{can_index} Communication Log - Run {self.timestamp}\n")
            self.can_files[can_index].write("# Format: [timestamp] SENDER DIRECTION: MUX_NAME (mux_id) | CAN_ID | PAYLOAD\n")
            self.can_files[can_index].write("# SENDER: act_XX (actuator ID) or host\n")
            self.can_files[can_index].write("#" + "="*80 + "\n\n")
            self.can_files[can_index].flush()
        
        return self.can_files[can_index]
    
    def _get_mux_name(self, mux: int) -> str:
        """Convert MUX ID to human-readable name."""
        mux_names = {
            Mux.PING: "PING",
            Mux.CONTROL: "CONTROL", 
            Mux.FEEDBACK: "FEEDBACK",
            Mux.MOTOR_ENABLE: "MOTOR_ENABLE",
            Mux.MOTOR_DISABLE: "MOTOR_DISABLE",
            Mux.FAULT_RESPONSE: "FAULT_RESPONSE"
        }
        return mux_names.get(mux, f"UNKNOWN_MUX_{mux:02X}")
    
    def _format_payload(self, payload: bytes) -> str:
        """Format payload bytes as hex string."""
        return " ".join(f"{b:02X}" for b in payload)
    
    def _format_can_id(self, can_id: int) -> str:
        """Format CAN ID with breakdown."""
        host_id = (can_id >> 0) & 0xFF
        actuator_can_id = (can_id >> 8) & 0xFF
        fault_flags = (can_id >> 16) & 0x3F
        mode_status = (can_id >> 22) & 0x03
        mux = (can_id >> 24) & 0x1F
        
        return (f"0x{can_id:08X} "
                f"(host={host_id:02X}, actuator={actuator_can_id:02X}, "
                f"faults={fault_flags:02X}, mode={mode_status}, mux={mux:02X})")
    
    def log_sent_message(self, can_index: int, can_id: int, mux: int, payload: bytes) -> None:
        """Log a CAN message being sent."""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]  # Include milliseconds
        mux_name = self._get_mux_name(mux)
        can_id_str = self._format_can_id(can_id)
        payload_str = self._format_payload(payload)
        
        # Extract actuator ID from CAN ID
        actuator_can_id = (can_id >> 8) & 0xFF
        sender = f"act_{actuator_can_id:02d}" if actuator_can_id != 0 else "host"
        
        log_file = self._get_can_file(can_index)
        log_file.write(f"[{timestamp}] {sender} TX: {mux_name} ({mux:02X}) | {can_id_str} | {payload_str}\n")
        log_file.flush()
    
    def log_received_message(self, can_index: int, parsed_frame: Dict[str, Any]) -> None:
        """Log a CAN message being received."""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]  # Include milliseconds
        mux = parsed_frame["mux"]
        mux_name = self._get_mux_name(mux)
        can_id = parsed_frame["host_id"] | (parsed_frame["actuator_can_id"] << 8) | (parsed_frame["fault_flags"] << 16) | (parsed_frame["mode_status"] << 22) | (mux << 24)
        can_id_str = self._format_can_id(can_id)
        payload_str = self._format_payload(parsed_frame["payload"])
        
        # Determine sender based on actuator ID
        actuator_can_id = parsed_frame["actuator_can_id"]
        sender = f"act_{actuator_can_id:02d}" if actuator_can_id != 0 else "host"
        
        log_file = self._get_can_file(can_index)
        log_file.write(f"[{timestamp}] {sender} RX: {mux_name} ({mux:02X}) | {can_id_str} | {payload_str}\n")
        log_file.flush()
    
    def log_feedback_data(self, can_index: int, actuator_can_id: int, feedback_data: Dict[str, Any]) -> None:
        """Log parsed feedback data in human-readable format."""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        sender = f"act_{actuator_can_id:02d}"
        
        log_file = self._get_can_file(can_index)
        log_file.write(f"[{timestamp}] {sender} FEEDBACK_DATA: Actuator {actuator_can_id} ({feedback_data.get('name', 'Unknown')})\n")
        log_file.write(f"  Angle: {feedback_data.get('angle', 0):.3f} rad\n")
        log_file.write(f"  Velocity: {feedback_data.get('velocity', 0):.3f} rad/s\n")
        log_file.write(f"  Torque: {feedback_data.get('torque', 0):.3f} Nm\n")
        log_file.write(f"  Temperature: {feedback_data.get('temperature', 0):.1f}°C\n")
        log_file.write(f"  Fault Flags: 0x{feedback_data.get('fault_flags', 0):02X}\n")
        log_file.write(f"  Cycle Age: {feedback_data.get('cycle_age', 0)}\n\n")
        log_file.flush()
    
    def log_control_command(self, can_index: int, actuator_can_id: int, angle: float, scaling: float, 
                          raw_angle: int, raw_ang_vel: int, raw_kp: int, raw_kd: int) -> None:
        """Log control command details."""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        sender = f"act_{actuator_can_id:02d}"
        
        log_file = self._get_can_file(can_index)
        log_file.write(f"[{timestamp}] {sender} CONTROL_COMMAND: Actuator {actuator_can_id}\n")
        log_file.write(f"  Target Angle: {angle:.3f} rad (raw: {raw_angle})\n")
        log_file.write(f"  Scaling: {scaling:.3f}\n")
        log_file.write(f"  Raw Values - Angle: {raw_angle}, Vel: {raw_ang_vel}, Kp: {raw_kp}, Kd: {raw_kd}\n\n")
        log_file.flush()
    
    def log_fault(self, can_index: int, actuator_can_id: int, fault_description: str, critical: bool) -> None:
        """Log fault information."""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        severity = "CRITICAL" if critical else "WARNING"
        sender = f"act_{actuator_can_id:02d}"
        
        log_file = self._get_can_file(can_index)
        log_file.write(f"[{timestamp}] {sender} FAULT: Actuator {actuator_can_id} - {severity}: {fault_description}\n")
        log_file.flush()
    
    def log_actuator_discovery(self, can_index: int, actuator_can_id: int) -> None:
        """Log actuator discovery during ping."""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        sender = f"act_{actuator_can_id:02d}"
        
        log_file = self._get_can_file(can_index)
        log_file.write(f"[{timestamp}] {sender} DISCOVERY: Found actuator {actuator_can_id}\n")
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


if __name__ == "__main__":
    # Test the logger
    logger = CanComLogger()
    
    # Simulate some CAN messages
    logger.log_sent_message(0, 0x8000FD00, Mux.PING, b"\x00" * 8)
    logger.log_received_message(0, {
        "host_id": 0xFD,
        "actuator_can_id": 0x0A,
        "fault_flags": 0x00,
        "mode_status": 0x00,
        "mux": Mux.PING,
        "payload": b"\x00" * 8
    })
    logger.log_feedback_data(0, 0x0A, {
        "name": "test_actuator",
        "angle": 1.234,
        "velocity": 0.567,
        "torque": 2.345,
        "temperature": 45.6,
        "fault_flags": 0x00,
        "cycle_age": 0
    })
    
    logger.close()
