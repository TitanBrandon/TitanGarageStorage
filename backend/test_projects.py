"""Persistent queue and proxy unit/integration checks; no scene quality claims."""

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from backend import projects
from backend.project_store import ProjectStore, StoreError
from backend.worker import JobCancelled, WorkerRunner, create_app, normalize_photo, runtime_status, validate_corrections, validate_outputs

TOKEN = "unit-test-worker-token-not-a-live-credential"


def photo():
    output = io.BytesIO()
    Image.new("RGB", (256, 192), (30, 40, 50)).save(output, "PNG")
    return output.getvalue()


class PersistentProjects(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = ProjectStore(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def create(self):
        return self.store.create(normalize_photo(photo()), "Garage")

    def test_reopen_from_fresh_store_keeps_source_and_job(self):
        project = self.create()
        reopened = ProjectStore(self.root)
        self.assertEqual(reopened.list()[0]["id"], project["id"])
        self.assertEqual(reopened.get(project["id"])["jobId"], project["jobId"])
        with Image.open(reopened.directory(project["id"]) / "source.jpg") as source:
            self.assertEqual(source.format, "JPEG")

    def test_single_live_lease_and_expired_job_recovery(self):
        project = self.create()
        job = self.store.lease_next("first-process")
        self.assertIsNone(ProjectStore(self.root).lease_next("second-process"))
        with self.store.connection() as db:
            db.execute("UPDATE jobs SET lease_until=0 WHERE id=?", (job["id"],))
        recovered = ProjectStore(self.root).lease_next("replacement-process")
        self.assertEqual(recovered["id"], project["jobId"])

    def test_queue_capacity_and_queued_cancellation_persist(self):
        self.store.max_queue = 1
        project = self.create()
        with self.assertRaises(StoreError) as raised:
            self.create()
        self.assertEqual(raised.exception.status, 429)
        self.store.cancel(project["id"])
        self.assertEqual(ProjectStore(self.root).get(project["id"])["state"], "cancelled")
        self.assertIsNone(self.store.lease_next("worker"))
        self.assertEqual(len(self.store.list()), 1)

    def test_rebuild_keeps_completed_assets_and_matching_scene_metadata(self):
        project = self.create()
        job = self.store.lease_next("worker")
        directory = self.store.revision_directory(project["id"], 1)
        directory.mkdir(parents=True)
        (directory / "scene.json").write_text(json.dumps({"room": {"width": 5}, "analysis": {"warnings": ["Estimated scale"]}}))
        (directory / "validated.json").write_text("{}")
        self.store.finish(job, "completed")
        revised = self.store.rebuild(project["id"], {"room": {"width": 7}})
        draft = self.store.revision_directory(project["id"], 2)
        draft.mkdir()
        (draft / "scene.json").write_text(json.dumps({"room": {"width": 7}}))
        detail = self.store.get(project["id"])
        self.assertEqual(detail["scene"]["room"]["width"], 5)
        self.assertEqual(detail["warnings"], ["Estimated scale"])
        self.assertIn("revision=1", detail["artifacts"]["glb"])
        self.assertEqual(revised["revision"], 2)

    def test_path_traversal_and_unvalidated_artifacts_are_rejected(self):
        project = self.create()
        with self.assertRaises(StoreError):
            self.store.asset("../secrets", "source")
        with self.assertRaises(StoreError):
            self.store.asset(project["id"], "glb")

    def test_real_child_process_is_killed_on_cancellation(self):
        self.create()
        job = self.store.lease_next("worker")
        directory = self.store.revision_directory(job["project_id"], 1)
        directory.mkdir(parents=True)
        runner = WorkerRunner(self.store)
        flag = threading.Event()
        timer = threading.Timer(0.2, flag.set)
        timer.start()
        try:
            with self.assertRaises(JobCancelled):
                runner.run_subprocess([sys.executable, "-c", "import time; time.sleep(60)"], job, directory, flag.is_set, "analyzing", 20)
            self.assertIsNotNone(runner.process.poll())
        finally:
            runner.kill_process()
            timer.join()

    def test_actual_child_timeout_does_not_leak_process(self):
        self.create()
        job = self.store.lease_next("worker")
        directory = self.store.revision_directory(job["project_id"], 1)
        directory.mkdir(parents=True)
        runner = WorkerRunner(self.store)
        with self.assertRaisesRegex(RuntimeError, "time limit"):
            runner.run_subprocess([sys.executable, "-c", "import time; time.sleep(60)"], job, directory, lambda: False, "analyzing", 0.2)
        self.assertIsNotNone(runner.process.poll())

    def test_worker_failure_records_real_child_diagnostic(self):
        self.create()
        job = self.store.lease_next("worker")
        directory = self.store.revision_directory(job["project_id"], 1)
        directory.mkdir(parents=True)
        runner = WorkerRunner(self.store)
        command = [sys.executable, "-c", "import json,sys; print(json.dumps({'stage':'failed','message':'No supported interior detected'})); sys.exit(1)"]
        with self.assertRaisesRegex(RuntimeError, "supported interior"):
            runner.run_subprocess(command, job, directory, lambda: False, "analyzing", 20)

    def test_failed_pipeline_job_is_persisted_for_page_reload(self):
        project = self.create()
        job = self.store.lease_next("worker")
        runner = WorkerRunner(self.store)
        with patch.object(runner, "run_subprocess", side_effect=RuntimeError("Unsupported photo; correct the room layout")):
            with self.assertLogs("titan.worker", level="ERROR"):
                runner.run(job)
        result = ProjectStore(self.root).get(project["id"])
        self.assertEqual(result["state"], "failed")
        self.assertIn("Unsupported photo", result["error"])

    def test_runtime_status_reports_missing_verified_model_and_blender(self):
        with patch("backend.model.MODEL_PATH", self.root / "missing.onnx"), patch("backend.worker.shutil.which", return_value=None):
            status = runtime_status()
        self.assertTrue(status["setupRequired"])
        self.assertFalse(status["ready"])
        self.assertIn("Blender executable", status["missing"])
        self.assertIn("verified depth model", status["missing"])

    def test_output_validation_rejects_file_existence_only(self):
        (self.root / "scene.glb").write_bytes(b"fake glb" * 8)
        with self.assertRaisesRegex(RuntimeError, "GLB header"):
            validate_outputs(self.root)

    def test_corrections_reject_nonfinite_and_unknown_geometry(self):
        with self.assertRaises(StoreError):
            validate_corrections({"room": {"width": float("nan")}})
        with self.assertRaises(StoreError):
            validate_corrections({"script": "run arbitrary code"})
        self.assertEqual(validate_corrections({"camera": {"fov": 55}, "room": {"height": 3}})["room"]["height"], 3)

    def test_worker_authentication_precedes_upload_parsing(self):
        with TestClient(create_app(self.root, start_runner=False, token=TOKEN)) as client:
            self.assertEqual(client.get("/healthz").status_code, 200)
            self.assertEqual(client.post("/api/projects", content=b"malformed").status_code, 401)
            self.assertEqual(client.get("/api/projects", headers={"Authorization": "Bearer " + TOKEN}).json(), {"projects": []})


class MockWorkerProxy(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {"WORKER_URL": "https://worker.example", "WORKER_TOKEN": TOKEN, "WORKER_ALLOW_HTTP": ""})
        self.environment.start()
        self.requests = []
        self.reply = lambda request: httpx.Response(200, json={"configured": True, "workerReachable": True, "setupRequired": False})

        def handle(request):
            self.requests.append(request)
            return self.reply(request)

        self.transport = httpx.MockTransport(handle)
        self.client_patch = patch.object(projects, "make_client", lambda: httpx.AsyncClient(transport=self.transport))
        self.client_patch.start()
        self.app = FastAPI()
        self.app.include_router(projects.router)
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.client_patch.stop()
        self.environment.stop()

    def test_proxy_uses_server_bearer_and_never_forwards_browser_auth(self):
        response = self.client.get("/api/projects/status", headers={"Authorization": "Basic private-site-login"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.requests[0].headers["Authorization"], "Bearer " + TOKEN)
        self.assertNotIn(TOKEN, response.text)
        self.assertEqual(str(self.requests[0].url), "https://worker.example/api/projects/status")

    def test_unconfigured_worker_requires_setup_without_ephemeral_fallback(self):
        with patch.dict(os.environ, {"WORKER_URL": "", "WORKER_TOKEN": ""}):
            status = self.client.get("/api/projects/status").json()
            self.assertFalse(status["configured"])
            self.assertTrue(status["setupRequired"])
            self.assertEqual(self.client.get("/api/projects").status_code, 503)
        self.assertEqual(self.requests, [])

    def test_external_plain_http_and_arbitrary_asset_paths_are_rejected(self):
        with patch.dict(os.environ, {"WORKER_URL": "http://worker.example"}):
            self.assertTrue(self.client.get("/api/projects/status").json()["setupRequired"])
        project_id = "10101010-1010-4010-8010-101010101010"
        self.assertEqual(self.client.get(f"/api/projects/{project_id}/assets/credentials").status_code, 404)
        self.assertEqual(self.requests, [])

    def test_proxy_sanitizes_worker_auth_failure_and_token_echo(self):
        self.reply = lambda request: httpx.Response(401, json={"detail": TOKEN}, headers={"X-Secret": TOKEN})
        response = self.client.get("/api/projects")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(TOKEN, response.text)
        self.reply = lambda request: httpx.Response(200, json={"detail": TOKEN})
        self.assertEqual(self.client.get("/api/projects").status_code, 502)

    def test_asset_stream_forwards_range_and_closes_without_leaking_token(self):
        self.reply = lambda request: httpx.Response(206, content=b"glTFtest", headers={"Content-Type": "model/gltf-binary", "Content-Range": "bytes 0-7/100", "X-Worker-Token": TOKEN})
        response = self.client.get("/api/projects/10101010-1010-4010-8010-101010101010/assets/glb?revision=1", headers={"Range": "bytes=0-7"})
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.content, b"glTFtest")
        self.assertEqual(self.requests[0].headers["Range"], "bytes=0-7")
        self.assertNotIn("x-worker-token", response.headers)


if __name__ == "__main__":
    unittest.main()
