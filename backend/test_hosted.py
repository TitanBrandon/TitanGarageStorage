"""Hosted authentication and durable-worker routing checks."""

import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.hosted import create_app

TEST_PASSWORD = "local-test-password-not-a-live-secret"


class HostedSite(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.assets = Path(self.directory.name)
        (self.assets / "index.html").write_text("<html><title>Space Studio test</title></html>")
        (self.assets / "bundle.js").write_text("console.log('test');")
        self.env = patch.dict(os.environ, {"SITE_PASSWORD": TEST_PASSWORD, "WORKER_URL": "", "WORKER_TOKEN": ""})
        self.env.start()
        self.context = TestClient(create_app(self.assets))
        self.client = self.context.__enter__()
        self.login = ("titan", TEST_PASSWORD)

    def tearDown(self):
        self.context.__exit__(None, None, None)
        self.env.stop()
        self.directory.cleanup()

    def test_health_check_is_public_and_contains_no_configuration(self):
        result = self.client.get("/healthz")
        self.assertEqual(result.json(), {"ready": True})

    def test_site_assets_and_api_require_the_site_login(self):
        for path in ["/", "/bundle.js", "/api/projects/status"]:
            with self.subTest(path=path):
                result = self.client.get(path)
                self.assertEqual(result.status_code, 401)
                self.assertIn("Basic", result.headers["www-authenticate"])
        result = self.client.post("/api/projects", content=b"not even parsed")
        self.assertEqual(result.status_code, 401)

    def test_correct_login_serves_frontend_and_nonsecret_api_status(self):
        result = self.client.get("/", auth=self.login)
        self.assertEqual(result.status_code, 200)
        self.assertIn("Space Studio test", result.text)
        result = self.client.get("/api/projects/status", auth=self.login)
        self.assertFalse(result.json()["configured"])
        self.assertTrue(result.json()["setupRequired"])
        self.assertEqual(result.headers["cache-control"], "no-store")
        self.assertNotIn(TEST_PASSWORD, result.text)

    def test_invalid_credentials_and_malformed_headers_fail_closed(self):
        for auth in [("someone", TEST_PASSWORD), ("titan", "wrong")]:
            self.assertEqual(self.client.get("/", auth=auth).status_code, 401)
        self.assertEqual(self.client.get("/", headers={"Authorization": "Basic malformed!"}).status_code, 401)

    def test_missing_worker_requires_setup(self):
        result = self.client.post("/api/projects", auth=self.login, files={"photo": ("photo.jpg", b"test", "image/jpeg")})
        self.assertEqual(result.status_code, 503)
        self.assertIn("WORKER_URL", result.json()["detail"])

    def test_upload_limits_and_cross_site_guard_are_retained(self):
        result = self.client.post("/api/projects", auth=self.login, headers={"Content-Length": "99999999"}, content=b"x")
        self.assertEqual(result.status_code, 413)
        result = self.client.post("/api/projects", auth=self.login, headers={"Sec-Fetch-Site": "cross-site"}, content=b"x")
        self.assertEqual(result.status_code, 403)

    def test_unknown_api_is_not_served_as_html(self):
        result = self.client.get("/api/missing", auth=self.login)
        self.assertEqual(result.status_code, 404)
        self.assertEqual(result.headers["content-type"], "application/json")

    def test_hosted_app_does_not_import_local_depth_dependencies(self):
        result = subprocess.run([sys.executable, "-c", "import sys; import backend.hosted; assert 'backend.app' not in sys.modules; assert 'onnxruntime' not in sys.modules"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


class RequiredConfiguration(unittest.TestCase):
    def test_server_refuses_to_start_without_a_site_password(self):
        with patch.dict(os.environ, {"SITE_PASSWORD": ""}):
            with self.assertRaisesRegex(RuntimeError, "SITE_PASSWORD"):
                with TestClient(create_app()):
                    pass


if __name__ == "__main__":
    unittest.main()
