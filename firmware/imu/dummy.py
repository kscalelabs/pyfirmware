import time


class DummyIMU:
    """Dummy IMU that returns zeros for teleop setups."""

    def __init__(self):
        print("⚠️  WARNING: No IMU device found")
        print("Use fixed output Dummy IMU? projected gravity = [0, 0, -9.81], gyro = [0, 0, 0] (y/n): ", end="")
        print("This may cause unstable behavior. Sure your policy doesn't need an IMU?(y/n): ", end="")
        response = input().strip().lower()
        if response != "y":
            print("Exiting...")
            raise SystemExit("User chose to exit due to missing IMU")

    def get_projected_gravity_and_gyroscope(self) -> tuple[tuple[float, ...], tuple[float, ...], float]:
        """Return dummy values for projected gravity and gyroscope."""
        return (0.0, 0.0, -9.81), (0.0, 0.0, 0.0), time.time()
