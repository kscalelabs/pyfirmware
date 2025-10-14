"""Hiwonder IMU reader using a background process and shared memory."""

import atexit
import mmap
from multiprocessing import Process, Event, Lock
import os
import struct
import time

import serial

# record layout: timestamp (double) + gyro (3 floats) + quaternion (4 floats)
RECORD_STRUCT = struct.Struct("<dfffffff")


def _open_mmap(path: str, size: int) -> mmap.mmap:
    """Open or create a shared memory map."""
    if not os.path.exists(path):
        with open(path, "wb") as f:
            f.write(b"\x00" * size)
    with open(path, "r+b") as f:
        return mmap.mmap(f.fileno(), size)


def _parse_gyro(data: bytes) -> tuple[float, float, float]:
    """Parse gyroscope data from IMU packet."""
    scale = 2000.0 * 3.14159 / 180.0 / 32768.0
    gx = struct.unpack("<h", data[2:4])[0] * scale
    gy = struct.unpack("<h", data[4:6])[0] * scale
    gz = struct.unpack("<h", data[6:8])[0] * scale
    return (gx, gy, gz)


def _parse_quat(data: bytes) -> tuple[float, float, float, float]:
    """Parse quaternion data from IMU packet."""
    qw = struct.unpack("<h", data[2:4])[0] / 32768.0
    qx = struct.unpack("<h", data[4:6])[0] / 32768.0
    qy = struct.unpack("<h", data[6:8])[0] / 32768.0
    qz = struct.unpack("<h", data[8:10])[0] / 32768.0
    return (qw, qx, qy, qz)


def _quat_to_gravity(q: tuple[float, float, float, float]) -> tuple[float, float, float]:
    """Convert quaternion to projected gravity vector."""
    w, x, y, z = q
    gx = 2 * (w * y - x * z) * 9.81
    gy = -2 * (w * x + y * z) * 9.81
    gz = -(w * w - x * x - y * y + z * z) * 9.81
    return (gx, gy, gz)


def _read_loop(device: str, baudrate: int, shm_path: str, shm_size: int,
               running: Event, lock: Lock) -> None:
    try:
        ser = serial.Serial(device, baudrate, timeout=0)
        shm = _open_mmap(shm_path, shm_size)
    except Exception:
        return

    gyro = (0.0, 0.0, 0.0)
    quat = (0.0, 0.0, 0.0, 0.0)

    while running.is_set():
        time.sleep(0.0001)
        if ser.read(1) == b"\x55":
            data = b"\x55" + ser.read(10)
            if len(data) == 11 and (sum(data[:10]) & 0xFF) == data[10]:
                if data[1] == 0x52:
                    gyro = _parse_gyro(data)
                elif data[1] == 0x59:
                    quat = _parse_quat(data)
                with lock:
                    shm.seek(0)
                    shm.write(RECORD_STRUCT.pack(time.time(), *gyro, *quat))

    ser.close()


class Hiwonder:
    def __init__(
        self, device: str = "/dev/ttyUSB0", baudrate: int = 230400, shm_path: str = "/dev/shm/imu_shm"
    ) -> None:
        self.shm = _open_mmap(shm_path, RECORD_STRUCT.size)
        self.lock = Lock()
        self.running = Event()
        self.running.set()

        self.proc = Process(
            target=_read_loop,
            args=(device, baudrate, shm_path, RECORD_STRUCT.size, self.running, self.lock),
            daemon=True,
        )
        self.proc.start()
        time.sleep(0.1)

        if not self.proc.is_alive():
            raise serial.SerialException(f"Failed to connect to {device}")

        atexit.register(self._cleanup)

    def _cleanup(self) -> None:
        try:
            self.running.clear()
            if self.proc.is_alive():
                self.proc.join(timeout=1.0)
                if self.proc.is_alive():
                    self.proc.terminate()
            self.shm.close()
        except Exception:
            pass

    def get_projected_gravity_and_gyroscope(self) -> tuple[tuple[float, ...], tuple[float, ...], float]:
        """Returns (projected_gravity, gyro, timestamp)."""
        with self.lock:
            self.shm.seek(0)
            data = self.shm.read(RECORD_STRUCT.size)

        if len(data) == RECORD_STRUCT.size:
            vals = RECORD_STRUCT.unpack(data)
            gyro = vals[1:4]
            quat = vals[4:8]
            gravity = _quat_to_gravity(quat)
            return gravity, gyro, vals[0]
        return (0.0, 0.0, -9.81), (0.0, 0.0, 0.0), 0.0


if __name__ == "__main__":
    imu = Hiwonder()
    t0 = time.time()
    while True:
        time.sleep(0.02)
        gravity, gyro, ts = imu.get_projected_gravity_and_gyroscope()
        print(f"gravity: {gravity}, gyro: {gyro}, t: {ts - t0:.3f}")
