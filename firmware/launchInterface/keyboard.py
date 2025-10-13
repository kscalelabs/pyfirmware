"""Keyboard-based launch interface for local robot control."""

import os
import sys
import termios
import tty
from pathlib import Path
from typing import Optional

from firmware.logger_general import Logger


class KeyboardLaunchInterface:
    """Simple launch interface for keyboard control without network connection."""
    
    def __init__(self):
        """Initialize keyboard launch interface."""
        self.logger = Logger()
        self.logger.info("Using keyboard launch interface")
    
    async def get_command_source(self) -> str:
        """Return the command source type."""
        self.logger.user_action("Select command source: (K) Keyboard, (U) UDP")
        
        # Temporarily restore normal terminal mode for input echo
        import termios, tty, sys
        try:
            # Get current (raw) settings
            current_settings = termios.tcgetattr(sys.stdin)
            # Create normal settings by modifying the raw ones
            normal_settings = current_settings[:]
            normal_settings[3] = normal_settings[3] | termios.ECHO  # Enable echo
            normal_settings[3] = normal_settings[3] & ~termios.ICANON  # Disable canonical mode
            # Apply normal settings
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, normal_settings)
        except:
            pass
        
        response = input("Enter choice: ").lower()
        if response == 'k':
            return "keyboard"
        elif response == 'u':
            return "udp"
        else:
            self.logger.error("Invalid choice. Please enter K or U")
            return None
    
    async def ask_imu_permission(self, imu_reader) -> bool:
        """Ask permission to continue without IMU. Returns True if should continue, False to abort."""
        if imu_reader is not None:
            self.logger.info("✅ IMU detected")
            return True
        
        self.logger.warning("No IMU hardware detected.")
        self.logger.user_action("Continue without IMU? (y/n): ")
        response = input("").lower()
        
        if response == 'y':
            self.logger.info("✅ Continuing without IMU")
            return True
        else:
            self.logger.warning("Aborted by user")
            return False
    
    async def ask_motor_permission(self, actuator_info) -> bool:
        """Ask permission to enable motors. Returns True if should enable, False to abort."""        
        # Temporarily restore normal terminal mode for input echo
        import termios, tty, sys
        try:
            # Get current (raw) settings
            current_settings = termios.tcgetattr(sys.stdin)
            # Create normal settings by modifying the raw ones
            normal_settings = current_settings[:]
            normal_settings[3] = normal_settings[3] | termios.ECHO  # Enable echo
            normal_settings[3] = normal_settings[3] & ~termios.ICANON  # Disable canonical mode
            # Apply normal settings
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, normal_settings)
        except:
            pass
        
        self.logger.user_action("Enable motors? (y/n): ")
        response = input("").lower()
        
        if response == 'y':
            self.logger.info("✅ Enabling motors...")
            return True
        else:
            self.logger.warning("Aborted by user")
            return False
    
    async def launch_policy_permission(self) -> bool:
        """Ask permission to start policy. Returns True if should start, False to abort."""
        self.logger.info("🚀 Ready to start policy")
        
        # Temporarily restore normal terminal mode for input echo
        import termios, tty, sys
        try:
            # Get current (raw) settings
            current_settings = termios.tcgetattr(sys.stdin)
            # Create normal settings by modifying the raw ones
            normal_settings = current_settings[:]
            normal_settings[3] = normal_settings[3] | termios.ECHO  # Enable echo
            normal_settings[3] = normal_settings[3] & ~termios.ICANON  # Disable canonical mode
            # Apply normal settings
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, normal_settings)
        except:
            pass
        
        self.logger.user_action("Start policy? (y/n): ")
        response = input("").lower()
        
        if response == 'y':
            self.logger.info("✅ Starting policy...")
            return True
        else:
            self.logger.warning("Aborted by user")
            return False
    
    async def get_kinfer_path(self) -> Optional[str]:
        """List available kinfer files and get user selection."""
        # Find all .kinfer files in ~/.policies
        policy_dir = Path.home() / ".policies"
        
        if not policy_dir.exists():
            self.logger.error(f"Policy directory not found: {policy_dir}")
            return None
        
        kinfer_files = list(policy_dir.glob("*.kinfer"))
        
        if not kinfer_files:
            self.logger.error(f"No kinfer files found in {policy_dir}")
            return None
        
        # Sort by modification time (newest first)
        kinfer_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        
        print("\nAvailable kinfer policies:")
        for i, filepath in enumerate(kinfer_files, 1):
            size_mb = filepath.stat().st_size / (1024 * 1024)
            print(f"  {i}. {filepath.name} ({size_mb:.2f} MB)")
        
        while True:
            try:
                choice = input(f"\nSelect policy (1-{len(kinfer_files)}): ").strip()
                idx = int(choice) - 1
                
                if 0 <= idx < len(kinfer_files):
                    selected = kinfer_files[idx]
                    return str(selected)
                else:
                    print(f"❌ Invalid choice. Please enter 1-{len(kinfer_files)}")
            except (ValueError, KeyboardInterrupt):
                print("\n❌ Aborted by user")
                return None
    
    async def close(self):
        """Close the interface (no-op for keyboard)."""
        self.logger.info("👋 Keyboard interface closed")