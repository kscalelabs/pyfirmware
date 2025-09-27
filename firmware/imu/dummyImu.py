import numpy as np
import time


class DummyIMU:
    """Dummy IMU that returns zeros when no real IMU is available."""
    
    def __init__(self):
        self.name = "DummyIMU"
    
    def get_projected_gravity_and_gyroscope(self):
        """Return zero values for gravity projection and gyroscope."""
        # Return zeros with the expected shape (3D vectors)
        projected_gravity = np.zeros(3, dtype=np.float32)
        gyroscope = np.zeros(3, dtype=np.float32)
        timestamp = time.time()
        return projected_gravity, gyroscope, timestamp