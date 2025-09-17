import math
import time

import numpy as np

# TODO deprecate this and move to policy


def apply_lowpass_filter(action: np.ndarray, lpf_carry: dict | None, cutoff_hz: float) -> tuple[np.ndarray, dict]:
    x = np.asarray(action, dtype=float)
    now = time.perf_counter()
    if lpf_carry is None:
        return x, {"prev": x.copy(), "t": now}

    dt = max(now - lpf_carry.get("t", now), 0.0)
    lpf_carry["t"] = now
    alpha = 1.0 - math.exp(-2.0 * math.pi * cutoff_hz * dt)
    y = lpf_carry["prev"] + alpha * (x - lpf_carry["prev"])
    lpf_carry["prev"] = y
    return y, lpf_carry
