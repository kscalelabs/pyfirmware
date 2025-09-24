import atexit
import mmap
import multiprocessing
import os
import signal
import struct
import time
from multiprocessing import Process

import serial


# record layout: timestamp (double) + gyro (3 floats) + quaternion (4 floats)
RECORD_STRUCT = struct.Struct("<dfffffff")


def open_or_create_mmap(path: str, size: int) -> mmap.mmap:
    """Create the file if missing and return an mmap of given size."""
    if not os.path.exists(path):
        with open(path, "wb") as f:
            f.write(b"\x00" * size)

    with open(path, "r+b") as f:
        return mmap.mmap(f.fileno(), size)


def quaternion_multiply(q1, q2):
    """Multiply two quaternions."""
    w1, x1, y1, z1 = q1
    w2, x2, y2, z2 = q2

    w = w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2
    x = w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2
    y = w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2
    z = w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2

    return (w, x, y, z)


def quaternion_to_projected_gravity(gravity, quaternion):
    """Rotate quaternion to projected gravity."""
    vx, vy, vz = gravity
    v_quat = (0.0, vx, vy, vz)
    q_conj = (quaternion[0], -quaternion[1], -quaternion[2], -quaternion[3])
    temp = quaternion_multiply(quaternion, v_quat)
    result_quat = quaternion_multiply(temp, q_conj)
    return (result_quat[1], result_quat[2], result_quat[3])


def parse_gyro(data):
    """Parse gyroscope data from IMU packet."""
    gx = struct.unpack("<h", data[2:4])[0] / 32768.0 * 2000.0 * 3.14159 / 180.0
    gy = struct.unpack("<h", data[4:6])[0] / 32768.0 * 2000.0 * 3.14159 / 180.0
    gz = struct.unpack("<h", data[6:8])[0] / 32768.0 * 2000.0 * 3.14159 / 180.0
    return (gx, gy, gz)


def parse_quaternion(data):
    """Parse quaternion data from IMU packet."""
    qw = struct.unpack("<h", data[2:4])[0] / 32768.0
    qx = struct.unpack("<h", data[4:6])[0] / 32768.0
    qy = struct.unpack("<h", data[6:8])[0] / 32768.0
    qz = struct.unpack("<h", data[8:10])[0] / 32768.0
    return (qw, qx, qy, qz)


class Hiwonder:
    """Reads IMU data from a serial port in a separate process and shares via shared memory."""

    def __init__(self, device="/dev/ttyUSB0", baudrate=230400, shm_path="/dev/shm/imu_shm"):
        # Serial configuration (child process will open the port)
        self.device = device
        self.baudrate = baudrate

        # Shared memory setup
        self.shm_path = shm_path
        self.shm_size = RECORD_STRUCT.size
        self.shm = open_or_create_mmap(self.shm_path, self.shm_size)
        self.shm_lock = multiprocessing.Lock()

        # Process management
        self.process = None
        self.running = multiprocessing.Event()

        # standard gravity
        self.gravity = (0.0, 0.0, -9.81)

        # Register clean shutdown hooks only for the main process
        self._register_shutdown_handlers()
        self.start()

    def _register_shutdown_handlers(self):
        """Register handlers for graceful shutdown on process termination."""

        def _safe_shutdown(*_args, **_kwargs):
            try:
                self.shm.close()
                if self.process is not None and self.process.is_alive():
                    self.running.clear()
                    self.process.join(timeout=1.0)
                    if self.process.is_alive():
                        self.process.terminate()
                    self.process = None
            except Exception:
                pass

        atexit.register(_safe_shutdown)
        signal.signal(signal.SIGTERM, _safe_shutdown)
        signal.signal(signal.SIGINT, _safe_shutdown)

    @staticmethod
    def _imu_reading_loop(device, baudrate, shm_path, shm_size, running_event, shm_lock):
        """Standalone IMU reading loop that runs in a separate process."""
        try:
            serial_conn = serial.Serial(device, baudrate, timeout=0)
        except Exception:
            return

        # Shared memory setup (child creates/opens and maps its own view)
        shm = open_or_create_mmap(shm_path, shm_size)

        last_gyro = (0.0, 0.0, 0.0)
        last_quaternion = (0.0, 0.0, 0.0, 0.0)

        while running_event.is_set():
            time.sleep(0.0001)

            # Read byte-by-byte until we find sync byte
            if serial_conn.read(1) == b"\x55":
                # Found sync, read remaining 10 bytes
                data = b"\x55" + serial_conn.read(10)

                if len(data) == 11 and (sum(data[:10]) & 0xFF) == data[10]:
                    timestamp = time.time()
                    if data[1] == 0x52:  # Gyro
                        last_gyro = parse_gyro(data)
                    elif data[1] == 0x59:  # Quaternion
                        last_quaternion = parse_quaternion(data)

                    packed_data = RECORD_STRUCT.pack(timestamp, *last_gyro, *last_quaternion)
                    with shm_lock:
                        shm.seek(0)
                        shm.write(packed_data)

        # Cleanup
        serial_conn.close()

    def start(self):
        """Start the IMU reading process."""
        if self.process is None or not self.process.is_alive():
            self.running.set()
            self.process = Process(
                target=self._imu_reading_loop,
                args=(self.device, self.baudrate, self.shm_path, self.shm_size, self.running, self.shm_lock),
            )
            # Ensure child exits if parent dies unexpectedly
            self.process.daemon = True
            self.process.start()

            # Give the process a moment to try connecting
            time.sleep(0.1)

            # Check if process died due to connection error
            if not self.process.is_alive():
                # Clean up the dead process
                self.process.join()
                self.process = None
                raise serial.SerialException(f"Failed to initialize IMU on {self.device}")

    def test(self):
        """Test function that runs the IMU reader and prints data."""
        self.start()
        start_time = time.time()
        while True:
            time.sleep(0.1)
            projgrav, gyro, timestamp = self.get_projected_gravity_and_gyroscope()
            print(
                f"projected_gravity: (\033[94m{projgrav[0]:.4f}\033[0m, \033[94m{projgrav[1]:.4f}\033[0m, \033[94m{projgrav[2]:.4f}\033[0m), gyro: (\033[92m{gyro[0]:.4f}\033[0m, \033[92m{gyro[1]:.4f}\033[0m, \033[92m{gyro[2]:.4f}\033[0m), timestamp: {timestamp - start_time:.3f}"
            )

    def get_projected_gravity_and_gyroscope(self) -> tuple[tuple[float, ...], tuple[float, ...], float]:
        """Get the latest projected gravity and gyroscope data from shared memory."""
        try:
            # Read from shared memory with lock
            with self.shm_lock:
                self.shm.seek(0)
                packed_data = self.shm.read(self.shm_size)

            if len(packed_data) == self.shm_size:
                # Unpack data: timestamp + gyro (3 floats) + quaternion (4 floats)
                unpacked_data = RECORD_STRUCT.unpack(packed_data)
                timestamp = unpacked_data[0]
                gyro = unpacked_data[1:4]
                quaternion = unpacked_data[4:8]
                proj_grav = quaternion_to_projected_gravity(self.gravity, quaternion)

                return proj_grav, gyro, timestamp
            else:
                # Return default values if shared memory is not properly initialized
                return (0.0, 0.0, -9.81), (0.0, 0.0, 0.0), 0.0

        except Exception as e:
            print(f"Error reading from shared memory: {e}")
            return (0.0, 0.0, -9.81), (0.0, 0.0, 0.0), 0.0


# for testing
if __name__ == "__main__":
    imu = Hiwonder()
    imu.test()


# TODO sometimes get imu takes 20ms or 35ms instead of 0.02ms