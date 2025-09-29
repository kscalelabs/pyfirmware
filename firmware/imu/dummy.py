import numpy as np
import time


class DummyIMU:
    """Dummy IMU that returns zeros for teleop setups."""
    
    def __init__(self):
        print("⚠️  WARNING: No IMU device found")
        print("Proceed with Dummy IMU? Returns fixed outputs: projected gravity = [0, 0, -9.81], gyro = [0, 0, 0] (y/n): ", end="")
        print("This may cause unstable behavior. Sure your policy doesn't need an IMU? Continue anyway? (y/n): ", end="")
        response = input().strip().lower()
        if response != 'y':
            print("Exiting...")
            raise SystemExit("User chose to exit due to missing IMU")
    
    def get_projected_gravity_and_gyroscope(self):
        """Return dummy values for projected gravity and gyroscope."""
        return np.array([0, 0, -9.81], dtype=np.float32), np.array([0, 0, 0], dtype=np.float32), time.time()