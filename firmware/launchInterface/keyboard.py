"""Keyboard-based launch interface for local robot control."""

from pathlib import Path
from typing import Any, Dict, Optional


class KeyboardLaunchInterface:
    """Simple launch interface for keyboard control without network connection."""

    def __init__(self) -> None:
        """Initialize keyboard launch interface."""
        print("Using keyboard launch interface")

    def get_command_source(self) -> str:
        """Return the command source type."""
        print("=================")
        print("Select command source: (K) Keyboard, (U) UDP")

        response = input("Enter choice: ").lower()
        print("=================")
        if response == "k":
            return "keyboard"
        elif response == "u":
            return "udp"
        else:
            print("Invalid choice. Please enter K or U")
            return None

    def ask_motor_permission(self, robot_config: Dict[str, Any]) -> bool:
        """Ask permission to enable motors. Returns True if should enable, False to abort."""
        imu_reader = robot_config.get("imu_reader")
        imu_name = imu_reader.__class__.__name__ if imu_reader is not None else "None"
        print("=================")
        print("Imu:", imu_name)
        response = input("Enable motors? (y/n): ").lower()
        if response == "n":
            print("=================")
            return False
        if robot_config.get("imu_reader") is None:
            imu_response = input("Are you sure? There is no IMU detected.").lower()
            if imu_response == "n":
                print("=================")
                return False
        print("=================")
        return True

    def launch_policy_permission(self) -> bool:
        """Ask permission to start policy. Returns True if should start, False to abort."""
        print("=================")
        print("🚀 Ready to start policy")

        print("Start policy? (y/n): ")
        response = input("").lower()
        print("=================")
        if response == "y":
            print("✅ Starting policy...")
            return True
        else:
            print("Aborted by user")
            return False

    def get_kinfer_path(self) -> Optional[str]:
        """List available kinfer files and get user selection."""
        # Find all .kinfer files in ~/.policies
        print("=================")
        policy_dir = Path.home() / ".policies"

        if not policy_dir.exists():
            print(f"Policy directory not found: {policy_dir}")
            return None

        kinfer_files = list(policy_dir.glob("*.kinfer"))

        if not kinfer_files:
            print(f"No kinfer files found in {policy_dir}")
            return None

        # Sort by modification time (newest first)
        kinfer_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

        print("\nAvailable kinfer policies:")
        for i, filepath in enumerate(kinfer_files, 1):
            size_mb = filepath.stat().st_size / (1024 * 1024)
            print(f"  {i}. {filepath.name} ({size_mb:.2f} MB)")
        print("=================")
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

    def close(self) -> None:
        """Close the interface (no-op for keyboard)."""
        print("👋 Keyboard interface closed")
