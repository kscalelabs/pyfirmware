import json
import math
import tarfile
import time

import numpy as np
import onnxruntime as ort

from imu.hiwonder import Hiwonder
from imu.bno055 import BNO055


def get_onnx_sessions(kinfer_path: str) -> tuple[ort.InferenceSession, ort.InferenceSession, dict]:
    print("Loading kinfer model from", kinfer_path)
    if not kinfer_path or not kinfer_path.endswith(".kinfer"):  # .tar.gz really
        raise ValueError("Model path must be provided and end with .kinfer")

    with tarfile.open(kinfer_path, "r:gz") as tar:
        assert tar.getnames() == ["init_fn.onnx", "step_fn.onnx", "metadata.json"]

        init_model_bytes = tar.extractfile("init_fn.onnx").read()
        step_model_bytes = tar.extractfile("step_fn.onnx").read()
        metadata = json.load(tar.extractfile("metadata.json"))
        print("kinfer model metadata:", metadata)

    print("Creating ONNX inference sessions...")
    init_session = ort.InferenceSession(init_model_bytes)
    step_session = ort.InferenceSession(step_model_bytes)

    init_inputs = init_session.get_inputs()
    init_outputs = init_session.get_outputs()
    step_inputs = step_session.get_inputs()
    step_outputs = step_session.get_outputs()

    print(f"\nInit fn - Inputs: {[inp.name for inp in init_inputs]}, Outputs: {[out.name for out in init_outputs]}")
    print(f"Step fn - Inputs: {[inp.name for inp in step_inputs]}, Outputs: {[out.name for out in step_outputs]}")

    # warm up step function
    step_dummy_inputs = {}
    for inp in step_inputs:
        step_dummy_inputs[inp.name] = np.zeros(inp.shape, dtype=np.float32)
    for _ in range(100):
        step_session.run(None, step_dummy_inputs)

    return init_session, step_session, metadata



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


def get_imu_reader():
    # try loading imus until one works
    try:
        return Hiwonder()
    except Exception as e:
        pass
    try:
        return BNO055()
    except Exception as e:
        pass
    raise ValueError("No IMU reader found")