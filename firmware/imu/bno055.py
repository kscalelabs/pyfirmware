"""BNO055 IMU reader using periphery I2C."""

import struct
import time

from periphery import I2C


class BNO055:
    NDOF_MODE = 0x0C  # for some reason this is faster than ACCGYRO_MODE
    MODE_REGISTER = 0x3D
    BLOCK_START = 0x08  # Base address for sensor data

    # Data offsets from BLOCK_START
    GYRO_OFFSET = 12
    GRAVITY_OFFSET = 38

    # Scale factors
    GYRO_SCALE = 0.001090830782496456
    GRAVITY_SCALE = 1 / 100.0

    def __init__(self, i2c_bus: str = "/dev/i2c-1", address: int = 0x28) -> None:
        self.i2c = I2C(i2c_bus)
        self.address = address
        self._write_register(self.MODE_REGISTER, bytes([self.NDOF_MODE]))
        time.sleep(0.01)

    def __del__(self) -> None:
        if hasattr(self, "i2c"):
            self.i2c.close()

    def _write_register(self, register: int, data: bytes) -> None:
        msgs = [I2C.Message(bytes([register]) + data)]
        self.i2c.transfer(self.address, msgs)

    def _read_register(self, register: int, length: int) -> bytes:
        msgs = [I2C.Message(bytes([register])), I2C.Message(bytearray(length), read=True)]
        self.i2c.transfer(self.address, msgs)
        return bytes(msgs[1].data)

    def get_projected_gravity_and_gyroscope(self) -> tuple[tuple[float, ...], tuple[float, ...], float]:
        """Read only gyro (rad/s) and gravity (m/s^2) vectors."""
        timestamp = time.time()
        gyro_bytes = self._read_register(self.BLOCK_START + self.GYRO_OFFSET, 6)
        grav_bytes = self._read_register(self.BLOCK_START + self.GRAVITY_OFFSET, 6)

        gyro = struct.unpack_from("<hhh", gyro_bytes, 0)
        gravity = struct.unpack_from("<hhh", grav_bytes, 0)

        gyro = tuple(g * self.GYRO_SCALE for g in gyro)
        gravity = tuple(-g * self.GRAVITY_SCALE for g in gravity)

        return gravity, gyro, timestamp


if __name__ == "__main__":
    sensor = BNO055()  # defaults to /dev/i2c-1

    while True:
        gravity, gyro, timestamp = sensor.get_projected_gravity_and_gyroscope()
        print(f"\033[37mGyro:\t{[f'{x:.3f}' for x in gyro]}\tGravity:\t{[f'{x:.3f}' for x in gravity]}\033[0m")
        time.sleep(0.1)
