"""World Labs protocol tests using MockTransport, never the paid live provider."""

import base64
import io
import json
import os
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from backend.app import app
from backend import worlds

MOCK_KEY = "mock-key-never-sent-to-a-live-provider"


def photo_bytes(format="WEBP", size=(320, 200), orientation=None):
    image = Image.new("RGB", size, (20, 40, 180))
    ImageDraw.Draw(image).rectangle((0, 0, size[0] // 2, size[1] // 2), fill=(220, 40, 10))
    output = io.BytesIO()
    exif = Image.Exif()
    if orientation:
        exif[274] = orientation
    image.save(output, format=format, exif=exif)
    return output.getvalue()


class WorldLabsMockProtocol(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = TestClient(app)
        cls.client = cls.context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.context.__exit__(None, None, None)

    def setUp(self):
        self.env = patch.dict(os.environ, {"WORLDLABS_API_KEY": MOCK_KEY, "WLT_API_KEY": ""})
        self.env.start()
        self.requests = []
        self.reply = lambda request: httpx.Response(200, json={"operation_id": "op-test"})

        def handle(request):
            self.requests.append(request)
            return self.reply(request)

        self.provider = worlds.WorldService(httpx.MockTransport(handle))
        self.service_patch = patch.object(worlds, "service", self.provider)
        self.service_patch.start()

    def tearDown(self):
        self.service_patch.stop()
        self.env.stop()

    def generate(self, **kwargs):
        return self.client.post("/api/worlds", files={"photo": ("garage.webp", photo_bytes(), "image/webp")}, **kwargs)

    def test_status_is_nonsecret_and_accepts_key_alias(self):
        response = self.client.get("/api/worlds/status")
        self.assertEqual(response.json(), {"configured": True, "provider": "World Labs"})
        self.assertNotIn(MOCK_KEY, response.text)
        with patch.dict(os.environ, {"WORLDLABS_API_KEY": "", "WLT_API_KEY": MOCK_KEY}):
            self.assertTrue(self.client.get("/api/worlds/status").json()["configured"])

    def test_missing_secret_blocks_paid_requests(self):
        with patch.dict(os.environ, {"WORLDLABS_API_KEY": "", "WLT_API_KEY": ""}):
            self.assertFalse(self.client.get("/api/worlds/status").json()["configured"])
            response = self.generate()
        self.assertEqual(response.status_code, 503)
        self.assertIn("WORLDLABS_API_KEY", response.json()["detail"])
        self.assertEqual(self.requests, [])

    def test_status_recovers_active_operation_without_browser_storage(self):
        self.assertEqual(self.generate().status_code, 202)
        response = self.client.get("/api/worlds/status")
        self.assertEqual(response.json()["activeOperationId"], "op-test")
        self.assertNotIn(MOCK_KEY, response.text)
        self.reply = lambda request: httpx.Response(200, json={"done": True, "error": {"code": 13}})
        self.assertEqual(self.client.get("/api/worlds/operations/op-test").json()["state"], "failed")
        self.assertNotIn("activeOperationId", self.client.get("/api/worlds/status").json())

    def test_image_submission_uses_real_photo_protocol_and_private_auth(self):
        response = self.generate()
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(response.json(), {"operationId": "op-test"})
        self.assertEqual(len(self.requests), 1)
        request = self.requests[0]
        self.assertEqual(str(request.url), worlds.API_BASE + "/worlds:generate")
        self.assertEqual(request.headers["WLT-Api-Key"], MOCK_KEY)
        body = json.loads(request.content)
        self.assertEqual(body["model"], "Marble 0.1-plus")
        self.assertEqual(body["world_prompt"]["type"], "image")
        self.assertFalse(body["world_prompt"]["disable_recaption"])
        image_prompt = body["world_prompt"]["image_prompt"]
        self.assertEqual(image_prompt["source"], "data_base64")
        self.assertEqual(image_prompt["extension"], "jpg")
        with Image.open(io.BytesIO(base64.b64decode(image_prompt["data_base64"]))) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertEqual(image.size, (320, 200))
            self.assertGreater(image.getpixel((25, 25))[0], 180)
            self.assertGreater(image.getpixel((250, 150))[2], 140)
        self.assertNotIn(MOCK_KEY, response.text)

    def test_mini_quality_is_explicit_and_invalid_quality_never_submits(self):
        response = self.generate(data={"quality": "mini"})
        self.assertEqual(response.status_code, 202)
        self.assertEqual(json.loads(self.requests[0].content)["model"], "Marble 0.1-mini")
        response = self.generate(data={"quality": "surprise"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(len(self.requests), 1)

    def test_duplicate_generation_blocked_until_terminal_poll(self):
        self.assertEqual(self.generate().status_code, 202)
        self.assertEqual(self.generate().status_code, 429)
        self.assertEqual(len(self.requests), 1)
        self.reply = lambda request: httpx.Response(200, json={"done": True, "error": {"message": MOCK_KEY}})
        response = self.client.get("/api/worlds/operations/op-test")
        self.assertEqual(response.json()["state"], "failed")
        self.assertNotIn(MOCK_KEY, response.text)
        self.assertIsNone(self.provider.active_operation)

    def test_poll_pending_then_ready_resolves_wrapped_world_and_assets(self):
        self.provider.active_operation = "op-test"
        self.reply = lambda request: httpx.Response(200, json={"done": False})
        self.assertEqual(self.client.get("/api/worlds/operations/op-test").json(), {"state": "pending"})
        self.assertEqual(self.provider.active_operation, "op-test")

        def completed(request):
            if "/operations/" in request.url.path:
                return httpx.Response(200, json={"done": True, "response": {"world_id": "world-test"}})
            return httpx.Response(200, json={"world": {"id": "world-test", "world_marble_url": "https://marble.worldlabs.ai/world/world-test", "assets": {"splats": {"spz_urls": {"500k": "https://cdn.marble.worldlabs.ai/world-test/500k.spz", "100k": "https://cdn.marble.worldlabs.ai/world-test/100k.spz"}}}}})

        self.reply = completed
        response = self.client.get("/api/worlds/operations/op-test")
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["state"], "ready")
        self.assertEqual(result["worldId"], "world-test")
        self.assertTrue(result["splatUrl"].endswith("500k.spz"))
        self.assertTrue(result["worldUrl"].startswith("https://marble.worldlabs.ai/"))
        self.assertIsNone(self.provider.active_operation)
        self.assertTrue(all(request.headers["WLT-Api-Key"] == MOCK_KEY for request in self.requests))

    def test_direct_world_and_alternate_response_id_are_supported(self):
        self.reply = lambda request: httpx.Response(200, json={"done": True, "response": {"id": "world-test"}}) if "/operations/" in request.url.path else httpx.Response(200, json={"id": "world-test", "assets": {"splats": {"spz_urls": {"100k": "https://cdn.marble.worldlabs.ai/test.spz"}}}})
        response = self.client.get("/api/worlds/operations/op-test")
        self.assertEqual(response.json()["state"], "ready")
        response = self.client.get("/api/worlds/world-test")
        self.assertEqual(response.json()["worldId"], "world-test")

    def test_provider_errors_are_actionable_without_response_leaks_or_retries(self):
        expected = {401: (503, "API key"), 403: (503, "API key"), 402: (402, "credits"), 429: (429, "limiting"), 500: (502, "service status")}
        for code, (local_status, message) in expected.items():
            with self.subTest(code=code):
                self.requests.clear()
                self.reply = lambda request, status=code: httpx.Response(status, json={"error": MOCK_KEY})
                response = self.generate()
                self.assertEqual(response.status_code, local_status, response.text)
                self.assertIn(message, response.json()["detail"])
                self.assertNotIn(MOCK_KEY, response.text)
                self.assertEqual(len(self.requests), 1)
                self.assertFalse(self.provider.submitting.locked())

    def test_submission_timeout_is_not_retried_and_warns_about_possible_charge(self):
        def timed_out(request):
            raise httpx.ReadTimeout("sensitive mock diagnostic: " + MOCK_KEY, request=request)

        self.reply = timed_out
        response = self.generate()
        self.assertEqual(response.status_code, 504)
        self.assertIn("may have accepted", response.json()["detail"])
        self.assertNotIn(MOCK_KEY, response.text)
        self.assertEqual(len(self.requests), 1)
        self.assertFalse(self.provider.submitting.locked())

    def test_invalid_photo_and_identifier_do_not_reach_provider(self):
        response = self.client.post("/api/worlds", files={"photo": ("bad.jpg", b"not an image", "image/jpeg")})
        self.assertEqual(response.status_code, 422)
        response = self.client.get("/api/worlds/operations/invalid.name")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.requests, [])

    def test_untrusted_or_non_https_provider_assets_are_not_exposed(self):
        self.reply = lambda request: httpx.Response(200, json={"id": "world-test", "world_marble_url": "javascript:alert(1)", "assets": {"splats": {"spz_urls": {"500k": "https://attacker.example/file.spz", "100k": "http://127.0.0.1/private"}}}})
        response = self.client.get("/api/worlds/world-test")
        self.assertEqual(response.json()["state"], "failed")
        self.assertIn("asset host", response.json()["message"])
        self.assertNotIn("splatUrl", response.json())
        self.assertNotIn("worldUrl", response.json())

    def test_photo_orientation_size_and_metadata_are_normalized(self):
        encoded = worlds.prepare_photo(photo_bytes("JPEG", (3000, 1500), orientation=6))
        with Image.open(io.BytesIO(base64.b64decode(encoded))) as image:
            self.assertEqual(image.size, (1024, 2048))
            self.assertFalse(image.getexif())


if __name__ == "__main__":
    unittest.main()
