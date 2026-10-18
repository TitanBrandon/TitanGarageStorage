"""Download metadata shared by setup and the inference server."""

from pathlib import Path

MODEL_NAME = "Depth Anything V2 Small"
MODEL_URL = (
    "https://github.com/fabio-sim/Depth-Anything-ONNX/releases/"
    "download/v2.0.0/depth_anything_v2_vits.onnx"
)
MODEL_SHA256 = "d2b11a11c1d4a12b47608fa65a17ee9a4c605b55ee1730c8e3b526304f2562be"
MODEL_BYTES = 99_373_606
MODEL_PATH = Path(__file__).resolve().parent / "models" / "depth_anything_v2_vits.onnx"
