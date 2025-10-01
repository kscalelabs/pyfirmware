"""Utility helpers."""

import json
import tarfile

import numpy as np
import onnxruntime as ort

from firmware.imu.bno055 import BNO055
from firmware.imu.dummy import DummyIMU
from firmware.imu.hiwonder import Hiwonder


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


def get_imu_reader():
    """Get an IMU reader, falling back to dummy IMU if none found."""
    try:
        return Hiwonder()
    except Exception:
        pass
    try:
        return BNO055()
    except Exception:
        pass
    try:
        return DummyIMU()
    except Exception:
        pass
