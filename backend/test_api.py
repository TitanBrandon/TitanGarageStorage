"""Meaningful local API checks, including an actual ONNX inference (no mocks)."""

import base64
import io
import unittest

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from backend.app import MAX_BODY_BYTES, app, engine


def scene_photo(orientation=None):
    image = Image.new("RGB", (400, 256), (130, 180, 220))
    draw = ImageDraw.Draw(image)
    draw.polygon([(0, 180), (200, 100), (400, 180), (400, 256), (0, 256)], fill=(100, 100, 100))
    draw.rectangle((40, 100, 120, 220), fill=(210, 40, 30))
    draw.rectangle((270, 80, 330, 170), fill=(220, 220, 210))
    output = io.BytesIO()
    exif = Image.Exif()
    if orientation:
        exif[274] = orientation
    image.save(output, format="JPEG", exif=exif)
    return output.getvalue()


class DepthAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = TestClient(app)
        cls.client = cls.context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.context.__exit__(None, None, None)

    def test_ready_model_is_loaded(self):
        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        self.assertTrue(health.json()["ready"], health.json())

    def test_real_inference_and_exif_orientation(self):
        response = self.client.post("/api/depth", files={"photo": ("scene.jpg", scene_photo(6), "image/jpeg")})
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual((result["width"], result["height"]), (256, 400))
        self.assertEqual(result["depthConvention"], "near-is-white")
        self.assertFalse(result["metric"])
        self.assertGreater(result["inferenceMs"], 0)
        png = base64.b64decode(result["depth"].split(",", 1)[1])
        with Image.open(io.BytesIO(png)) as depth:
            self.assertEqual(depth.size, (256, 400))
            self.assertEqual(depth.format, "PNG")
            self.assertGreater(np.asarray(depth).std(), 10)

    def test_invalid_photo_is_rejected(self):
        response = self.client.post("/api/depth", files={"photo": ("fake.jpg", b"not a photo", "image/jpeg")})
        self.assertEqual(response.status_code, 422)

    def test_empty_photo_is_rejected(self):
        response = self.client.post("/api/depth", files={"photo": ("empty.png", b"", "image/png")})
        self.assertEqual(response.status_code, 422)

    def test_small_photo_is_rejected(self):
        output = io.BytesIO()
        Image.new("RGB", (20, 20)).save(output, format="PNG")
        response = self.client.post("/api/depth", files={"photo": ("small.png", output.getvalue(), "image/png")})
        self.assertEqual(response.status_code, 422)

    def test_oversized_body_is_rejected_before_multipart_parse(self):
        response = self.client.post("/api/depth", content=b"x", headers={"Content-Length": str(MAX_BODY_BYTES + 1)})
        self.assertEqual(response.status_code, 413)

    def test_cross_site_browser_upload_is_rejected(self):
        response = self.client.post("/api/depth", files={"photo": ("scene.jpg", scene_photo(), "image/jpeg")}, headers={"Sec-Fetch-Site": "cross-site"})
        self.assertEqual(response.status_code, 403)

    def test_concurrent_inference_is_bounded(self):
        engine.busy.acquire()
        try:
            response = self.client.post("/api/depth", files={"photo": ("scene.jpg", scene_photo(), "image/jpeg")})
            self.assertEqual(response.status_code, 429)
        finally:
            engine.busy.release()


if __name__ == "__main__":
    unittest.main()
