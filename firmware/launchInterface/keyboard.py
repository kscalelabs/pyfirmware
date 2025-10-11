"""Keyboard-based launch interface for local robot control."""

import os
from pathlib import Path
from typing import Optional


class KeyboardLaunchInterface:
    """Simple launch interface for keyboard control without network connection."""
    
    def __init__(self):
        """Initialize keyboard launch interface."""
        print("⌨️  Using keyboard launch interface")
    
    async def getCommandSource(self) -> str:
        """Return the command source type."""
        return "keyboard"
    
    async def askIMUPermission(self, imu_reader) -> bool:
        """Ask permission to continue without IMU. Returns True if should continue, False to abort."""
        print(f"IMU reader: {imu_reader}")
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
    
    async def askMotorPermission(self, actuator_info) -> bool:
        """Ask permission to enable motors. Returns True if should enable, False to abort."""
        print(f"🤖 Found actuators: {actuator_info}")
        response = input("Enable motors? (y/n): ").lower()
        
        if response == 'y':
            print("✅ Enabling motors...")
            return True
        else:
            print("❌ Aborted by user")
            return False
    
    async def launchPolicyPermission(self) -> bool:
        """Ask permission to start policy. Returns True if should start, False to abort."""
        print("🚀 Ready to start policy")
        response = input("Start policy? (y/n): ").lower()
        
        if response == 'y':
            print("✅ Starting policy...")
            return True
        else:
            print("❌ Aborted by user")
            return False
    
    async def getKinferPath(self) -> Optional[str]:
        """List available kinfer files and get user selection."""
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
        
        print("\n📋 Available kinfer policies:")
        for i, filepath in enumerate(kinfer_files, 1):
            size_mb = filepath.stat().st_size / (1024 * 1024)
            print(f"  {i}. {filepath.name} ({size_mb:.2f} MB)")
        
        while True:
            try:
                choice = input(f"\nSelect policy (1-{len(kinfer_files)}): ").strip()
                idx = int(choice) - 1
                
                if 0 <= idx < len(kinfer_files):
                    selected = kinfer_files[idx]
                    print(f"✅ Selected: {selected.name}")
                    return str(selected)
                else:
                    print(f"❌ Invalid choice. Please enter 1-{len(kinfer_files)}")
            except (ValueError, KeyboardInterrupt):
                print("\n❌ Aborted by user")
                return None
    
    async def close(self):
        """Close the interface (no-op for keyboard)."""
        print("👋 Keyboard interface closed")

