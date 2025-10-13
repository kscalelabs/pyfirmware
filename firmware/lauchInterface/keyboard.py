"""Keyboard-based launch interface for local robot control."""

import os
import sys
import termios
import tty
from pathlib import Path
from typing import Optional


class KeyboardLaunchInterface:
    """Simple launch interface for keyboard control without network connection."""
    
    def __init__(self):
        """Initialize keyboard launch interface."""
        print("⌨️  Using keyboard launch interface")
    
    async def get_command_source(self) -> str:
        """Return the command source type."""
        print("Select command source: (K) Keyboard, (U) UDP")
        response = input("Enter choice: ").lower()
        if response == 'k':
            return "keyboard"
        elif response == 'u':
            return "udp"
        else:
            print("❌ Invalid choice. Please enter K or U")
            return None
    
    async def ask_imu_permission(self, imu_reader) -> bool:
        """Ask permission to continue without IMU. Returns True if should continue, False to abort."""
        if imu_reader is not None:
            print("✅ IMU detected")
            return True
        
        print("⚠️  No IMU hardware detected.")
        response = input("Continue without IMU? (y/n): ").lower()
        
        if response == 'y':
            print("✅ Continuing without IMU")
            return True
        else:
            print("❌ Aborted by user")
            return False
    
    async def ask_motor_permission(self, actuator_info) -> bool:
        """Ask permission to enable motors. Returns True if should enable, False to abort."""
        print(f"🤖 Found actuators: {actuator_info}")
        response = input("Enable motors? (y/n): ").lower()
        
        if response == 'y':
            print("✅ Enabling motors...")
            return True
        else:
            print("❌ Aborted by user")
            return False
    
    async def launch_policy_permission(self) -> bool:
        """Ask permission to start policy. Returns True if should start, False to abort."""
        print("🚀 Ready to start policy")
        response = input("Start policy? (y/n): ").lower()
        
        if response == 'y':
            print("✅ Starting policy...")
            return True
        else:
            print("❌ Aborted by user")
            return False
    
    async def get_kinfer_path(self) -> Optional[str]:
        """Interactive kinfer file selection with arrow keys and filtering."""
        # Find all .kinfer files in ~/.policies
        policy_dir = Path.home() / ".policies"
        
        if not policy_dir.exists():
            print(f"❌ Policy directory not found: {policy_dir}")
            return None
        
        kinfer_files = list(policy_dir.glob("*.kinfer"))
        
        if not kinfer_files:
            print(f"❌ No kinfer files found in {policy_dir}")
            return None
        
        # Sort by modification time (newest first)
        kinfer_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        
        return self._interactive_file_selector(kinfer_files)
    
    def _interactive_file_selector(self, files: list[Path]) -> Optional[str]:
        """Interactive file selector with arrow keys and filtering."""
        if not files:
            return None
            
        filter_text = ""
        selected_idx = 0
        filtered_files = files.copy()
        
        # Save terminal settings
        old_settings = termios.tcgetattr(sys.stdin)
        try:
            tty.setraw(sys.stdin.fileno())
            
            while True:
                self._display_file_list(filtered_files, selected_idx, filter_text)
                
                # Read single character
                ch = sys.stdin.read(1)
                
                if ch == '\x1b':  # ESC sequence
                    ch2 = sys.stdin.read(1)
                    if ch2 == '[':
                        ch3 = sys.stdin.read(1)
                        if ch3 == 'A':  # Up arrow
                            selected_idx = max(0, selected_idx - 1)
                        elif ch3 == 'B':  # Down arrow
                            selected_idx = min(len(filtered_files) - 1, selected_idx + 1)
                elif ch == '\r' or ch == '\n':  # Enter
                    if filtered_files:
                        selected = filtered_files[selected_idx]
                        print(f"\n✅ Selected: {selected.name}")
                        return str(selected)
                elif ch == '\x7f' or ch == '\b':  # Backspace
                    if filter_text:
                        filter_text = filter_text[:-1]
                        filtered_files, selected_idx = self._apply_filter(files, filter_text, selected_idx)
                elif ch == '\x03':  # Ctrl+C
                    print("\n❌ Aborted by user")
                    return None
                elif ch.isprintable():  # Printable character
                    filter_text += ch
                    filtered_files, selected_idx = self._apply_filter(files, filter_text, selected_idx)
                    
        except KeyboardInterrupt:
            print("\n❌ Aborted by user")
            return None
        finally:
            # Restore terminal settings
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
            print()  # New line after raw mode
    
    def _apply_filter(self, files: list[Path], filter_text: str, current_idx: int) -> tuple[list[Path], int]:
        """Apply filter and adjust selection index."""
        if not filter_text:
            filtered = files.copy()
        else:
            filtered = [f for f in files if filter_text.lower() in f.name.lower()]
        
        # Adjust selected index to stay within bounds
        new_idx = min(current_idx, len(filtered) - 1) if filtered else 0
        
        return filtered, new_idx
    
    def _display_file_list(self, files: list[Path], selected_idx: int, filter_text: str):
        """Display the file list with current selection highlighted."""
        # Clear screen and move cursor to top
        print('\033[2J\033[H', end='')
        
        print("📋 Available kinfer policies:")
        if filter_text:
            print(f"🔍 Filter: '{filter_text}'")
        print("Use ↑↓ arrows to navigate, Enter to select, type to filter, Ctrl+C to cancel")
        print()
        
        if not files:
            print("❌ No files match the filter")
            return
            
        for i, filepath in enumerate(files):
            size_mb = filepath.stat().st_size / (1024 * 1024)
            modified = filepath.stat().st_mtime
            
            if i == selected_idx:
                # Highlighted selection
                print(f"\033[7m  ▶ {filepath.name} ({size_mb:.2f} MB)\033[0m")
            else:
                print(f"    {filepath.name} ({size_mb:.2f} MB)")
        
        print(f"\n{len(files)} file{'s' if len(files) != 1 else ''} found")
    
    async def close(self):
        """Close the interface (no-op for keyboard)."""
        print("👋 Keyboard interface closed")
