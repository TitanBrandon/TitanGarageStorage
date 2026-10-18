"""Repeat the actual Docker + browser reconstruction checks on Linux.

Run with the project's Python 3.12 environment:
  python scripts/validate_pipeline.py --cloud-network
  python scripts/validate_pipeline.py --skip-build

Docker, npm dependencies, Playwright Chromium and validation/photos fixtures must
already be installed. This creates unique owned containers on ports 8022/8023,
restarts the real worker to check durable project persistence, then removes its
containers. Its uniquely named data volume is retained; runtime.json records the
exact cleanup command. Existing development/validation services are untouched.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import signal
import shutil
import socket
import subprocess
import sys
import threading
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "validation/results"


def arguments():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cloud-network", action="store_true", help="Use the verified cloud proxy/certificate build helper.")
    parser.add_argument("--skip-build", action="store_true", help="Use existing final images; do not rebuild them.")
    parser.add_argument("--web-image", default="titan-space-studio:hosted")
    parser.add_argument("--worker-image", default="titan-space-studio:worker")
    parser.add_argument("--worker-port", type=int, default=8022)
    parser.add_argument("--web-port", type=int, default=8023)
    return parser.parse_args()


class ValidationRun:
    def __init__(self, args):
        self.args = args
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(3)
        self.worker = "titan-validation-worker-" + self.run_id.lower()
        self.web = "titan-validation-web-" + self.run_id.lower()
        self.volume = "titan-validation-data-" + self.run_id.lower()
        self.password, self.token = secrets.token_urlsafe(32), secrets.token_urlsafe(40)
        self.docker = ["docker"] + (["--config", "/workspace/.docker"] if args.cloud_network else [])
        self.created = []
        self.samples = []
        self.stats_done = threading.Event()
        self.stats_thread = None
        self.report = {
            "runId": self.run_id,
            "startedAt": datetime.now(timezone.utc).isoformat(),
            "kind": "actual Docker worker + authenticated production web + Playwright browser",
            "webURL": f"http://127.0.0.1:{args.web_port}",
            "workerURL": f"http://127.0.0.1:{args.worker_port}",
            "resourceLimits": {"workerMemory": "8g", "workerCPUs": 4, "webMemory": "512m", "webCPUs": 1},
            "volume": self.volume,
            "retainedVolumeCleanup": "docker volume rm " + self.volume,
            "cloudNetwork": args.cloud_network,
            "skippedBuild": args.skip_build,
            "allPassed": False,
        }

    def redact(self, value):
        text = str(value)
        for secret in (self.password, self.token):
            text = text.replace(secret, "[REDACTED]")
        return text

    def call(self, command, *, env=None, log=None, check=True):
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, start_new_session=True)
        output = []
        destination = (RESULTS / log).open("w") if log else None
        try:
            for line in process.stdout:
                line = self.redact(line)
                output.append(line)
                if destination:
                    destination.write(line)
                print(line, end="", flush=True)
            returncode = process.wait()
        except BaseException:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
            raise
        finally:
            if destination:
                destination.close()
        if check and returncode:
            raise RuntimeError("Validation command failed with exit code " + str(returncode) + ": " + command[0])
        return returncode, "".join(output)

    def capture(self, command, check=True):
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        if check and result.returncode:
            raise RuntimeError(self.redact(result.stderr.strip() or "A validation command failed."))
        return self.redact(result.stdout.strip())

    def preflight(self):
        if not sys.platform.startswith("linux"):
            raise RuntimeError("This host-network validation script requires Linux Docker. Use the portable worker Compose stack on other hosts.")
        for executable in ("docker", "npm"):
            if not shutil.which(executable):
                raise RuntimeError("Install " + executable + " before running validation.")
        for name in ("warehouse", "room"):
            if not (ROOT / f"validation/photos/{name}.jpg").is_file():
                raise RuntimeError("Missing permitted fixture: validation/photos/" + name + ".jpg")
        if self.args.worker_port == self.args.web_port:
            raise RuntimeError("The worker and web validation ports must differ.")
        for port in (self.args.worker_port, self.args.web_port):
            if not 1024 <= port <= 65535:
                raise RuntimeError("Validation ports must be between 1024 and 65535.")
            try:
                with socket.socket() as listener:
                    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    listener.bind(("127.0.0.1", port))
            except OSError:
                raise RuntimeError(f"Port {port} is already in use; choose another validation port. Existing services were left running.") from None
        self.report["dockerVersion"] = self.capture(self.docker + ["version", "--format", "{{.Server.Version}}"])
        self.report["nodeVersion"] = self.capture(["node", "--version"])

    def build(self):
        if self.args.skip_build:
            return
        for filename, tag, log in (("Dockerfile", self.args.web_image, "docker-web-build.log"), ("Dockerfile.worker", self.args.worker_image, "docker-worker-build.log")):
            print("Building " + filename + " using the repository's trust-preserving build helper.", flush=True)
            command = [sys.executable, "scripts/build_hosted.py", "--file", filename, "--tag", tag]
            if self.args.cloud_network:
                command.append("--cloud-network")
            self.call(command, log=log)

    def start(self):
        self.report["images"] = {
            "web": {"tag": self.args.web_image, "id": self.capture(self.docker + ["image", "inspect", "--format", "{{.Id}}", self.args.web_image])},
            "worker": {"tag": self.args.worker_image, "id": self.capture(self.docker + ["image", "inspect", "--format", "{{.Id}}", self.args.worker_image])},
        }
        self.capture(self.docker + ["volume", "create", "--label", "titan.validation.run=" + self.run_id, self.volume])
        worker_env = os.environ.copy()
        worker_env.update(WORKER_TOKEN=self.token, PROJECTS_DIR="/data/projects", PORT=str(self.args.worker_port))
        command = self.docker + ["run", "-d", "--pull=never", "--init", "--name", self.worker, "--label", "titan.validation.run=" + self.run_id, "--network=host", "--memory=8g", "--cpus=4", "--mount", "type=volume,src=" + self.volume + ",dst=/data"]
        for name in ("WORKER_TOKEN", "PROJECTS_DIR", "PORT"):
            command += ["--env", name]
        self.capture_env(command + [self.args.worker_image], worker_env)
        self.created.append(self.worker)
        web_env = os.environ.copy()
        web_env.update(SITE_PASSWORD=self.password, WORKER_TOKEN=self.token, WORKER_URL=self.report["workerURL"], PORT=str(self.args.web_port))
        command = self.docker + ["run", "-d", "--pull=never", "--init", "--name", self.web, "--label", "titan.validation.run=" + self.run_id, "--network=host", "--memory=512m", "--cpus=1"]
        for name in ("SITE_PASSWORD", "WORKER_TOKEN", "WORKER_URL", "PORT"):
            command += ["--env", name]
        self.capture_env(command + [self.args.web_image], web_env)
        self.created.append(self.web)
        self.wait_ready()
        versions = self.capture(self.docker + ["exec", self.worker, "python", "-c", "import importlib.metadata,json,sys; print(json.dumps({'python':sys.version.split()[0], 'packages':{name:importlib.metadata.version(name) for name in ['numpy','onnxruntime','Pillow','opencv-python-headless','fastapi','httpx']}}))"])
        self.report["workerVersions"] = json.loads(versions)
        self.report["blenderVersion"] = self.capture(self.docker + ["exec", self.worker, "blender", "--background", "--version"]).splitlines()[0]
        self.stats_thread = threading.Thread(target=self.sample_stats, daemon=True)
        self.stats_thread.start()

    def capture_env(self, command, env):
        # Secrets are passed by environment NAME, never as command-line values.
        result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(self.redact(result.stderr or "The validation container could not start."))

    def wait_ready(self, timeout=90):
        deadline = time.monotonic() + timeout
        with httpx.Client(base_url=self.report["webURL"], auth=("titan", self.password), timeout=4) as client:
            while time.monotonic() < deadline:
                try:
                    response = client.get("/api/projects/status")
                    if response.status_code == 200:
                        payload = response.json()
                        if payload.get("workerReachable") and not payload.get("setupRequired"):
                            self.report["readiness"] = payload
                            return
                except (httpx.RequestError, ValueError):
                    pass
                time.sleep(.4)
        raise RuntimeError("The production containers did not report a ready Blender worker within the startup limit.")

    def sample_stats(self):
        while not self.stats_done.is_set():
            try:
                result = self.capture(self.docker + ["stats", "--no-stream", "--format", "{{json .}}", self.worker, self.web], check=False)
                self.samples.append({"time": datetime.now(timezone.utc).isoformat(), "containers": [json.loads(line) for line in result.splitlines() if line]})
            except (ValueError, RuntimeError):
                pass
            self.stats_done.wait(2)

    def browser_tests(self):
        environment = os.environ.copy()
        environment.update(TITAN_TEST_BASE_URL=self.report["webURL"], TITAN_TEST_SITE_PASSWORD=self.password)
        print("Running actual production photo pipelines and browser navigation checks.", flush=True)
        exit_code, _ = self.call(["npm", "test", "--", "tests/studio.spec.ts", "tests/ui-contract.spec.ts", "--reporter=line"], env=environment, log="browser-tests.log", check=False)
        self.report["browserTestsExitCode"] = exit_code
        return exit_code

    def durability(self):
        with httpx.Client(base_url=self.report["webURL"], auth=("titan", self.password), timeout=30) as client:
            response = client.get("/api/projects")
            response.raise_for_status()
            before = response.json()["projects"]
            completed = [project for project in before if project["state"] == "completed"]
            if len(completed) < 2:
                raise RuntimeError("Both actual photo pipelines must complete before durability can pass.")
            print("Restarting the owned worker and reopening its durable completed projects.", flush=True)
            self.capture(self.docker + ["restart", "--time", "45", self.worker])
            self.wait_ready()
            response = client.get("/api/projects")
            response.raise_for_status()
            after = {project["id"]: project for project in response.json()["projects"]}
            reopened = []
            for project in completed:
                if project["id"] not in after or after[project["id"]]["state"] != "completed":
                    raise RuntimeError("A completed project did not survive the actual worker restart.")
                detail = client.get("/api/projects/" + project["id"])
                detail.raise_for_status()
                model = client.get(detail.json()["artifacts"]["glb"])
                model.raise_for_status()
                if model.content[:4] != b"glTF":
                    raise RuntimeError("A reopened project did not return a GLB artifact.")
                reopened.append({"id": project["id"], "state": "completed", "glbBytes": len(model.content)})
            self.report["durability"] = {"passed": True, "workerRestarted": True, "reopenedProjects": reopened}
            self.report["projects"] = [{key: project.get(key) for key in ("id", "name", "state", "stage", "revision")} for project in after.values()]

    def cleanup(self):
        self.stats_done.set()
        if self.stats_thread:
            self.stats_thread.join(timeout=5)
        self.report["resourceSamples"] = self.samples
        removed = []
        for name in reversed(self.created):
            owner = self.capture(self.docker + ["inspect", "--format", '{{ index .Config.Labels "titan.validation.run" }}', name], check=False)
            if owner != self.run_id:
                continue
            # Docker sends log output on stderr too; capture both without exposing secrets.
            result = subprocess.run(self.docker + ["logs", name], capture_output=True, text=True)
            (RESULTS / ("worker-runtime.log" if name == self.worker else "web-runtime.log")).write_text(self.redact(result.stdout + result.stderr))
            self.capture(self.docker + ["stop", "--time", "45", name], check=False)
            self.capture(self.docker + ["rm", name], check=False)
            removed.append(name)
        self.report["removedOwnedContainers"] = removed
        self.report["retainedVolume"] = self.volume
        if self.report.get("durability", {}).get("passed") and len(removed) == 2:
            # A restart retains a container's writable layer too. Reopen the
            # independent named volume from a NEW container after both original
            # containers are gone, to establish that storage really is external.
            probe = """
import json, sqlite3
from pathlib import Path
root=Path('/data/projects')
db=sqlite3.connect('file:/data/projects/projects.sqlite3?mode=ro', uri=True)
rows=db.execute("SELECT id,completed_revision FROM projects WHERE state='completed'").fetchall()
assert len(rows)>=2, 'Completed projects missing from persistent volume'
for project_id, revision in rows:
    folder=root/project_id/'revisions'/str(revision)
    assert (folder/'scene.glb').read_bytes()[:4]==b'glTF'
    assert (folder/'scene.blend').read_bytes()[:7]==b'BLENDER'
print(json.dumps({'passed':True,'newContainer':True,'originalContainersRemoved':True,'completedProjects':len(rows)}))
"""
            # SQLite opens the DB logically read-only, but WAL mode may need a
            # shared-memory sidecar in its writable production directory.
            result = self.capture(self.docker + ["run", "--rm", "--pull=never", "--network=none", "--mount", "type=volume,src=" + self.volume + ",dst=/data", "--entrypoint", "python", self.args.worker_image, "-c", probe])
            self.report["independentVolumeReopen"] = json.loads(result)


def main():
    args = arguments()
    RESULTS.mkdir(parents=True, exist_ok=True)
    run = ValidationRun(args)
    started = time.monotonic()
    try:
        run.preflight()
        run.build()
        run.start()
        result = run.browser_tests()
        run.durability()
        run.report["allPassed"] = result == 0
    except (Exception, KeyboardInterrupt) as error:
        run.report["failure"] = run.redact(str(error) or type(error).__name__)
        print("Validation did not pass: " + run.report["failure"], flush=True)
    finally:
        try:
            run.cleanup()
        except Exception as error:
            run.report["cleanupFailure"] = run.redact(str(error))
            run.report["allPassed"] = False
        run.report["elapsedSeconds"] = round(time.monotonic() - started, 2)
        run.report["finishedAt"] = datetime.now(timezone.utc).isoformat()
        (RESULTS / "runtime.json").write_text(run.redact(json.dumps(run.report, indent=2)) + "\n")
    print("Runtime evidence: validation/results/runtime.json", flush=True)
    print("Retained validation volume cleanup: docker volume rm " + run.volume, flush=True)
    return 0 if run.report["allPassed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
