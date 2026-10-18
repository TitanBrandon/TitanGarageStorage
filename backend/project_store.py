"""Durable project/job metadata and generated assets on one persistent volume."""

from contextlib import contextmanager
import json
from pathlib import Path
import shutil
import sqlite3
import time
import uuid


class StoreError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message
        super().__init__(message)


def valid_id(value: str) -> str:
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise StoreError(422, "Invalid project ID.") from None
    return value


class ProjectStore:
    def __init__(self, root: Path, max_queue=16):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "projects.sqlite3"
        self.max_queue = max_queue
        with self.connection() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, state TEXT NOT NULL,
                    stage TEXT NOT NULL, progress REAL NOT NULL DEFAULT 0,
                    revision INTEGER NOT NULL DEFAULT 1, completed_revision INTEGER,
                    active_job TEXT, corrections TEXT NOT NULL DEFAULT '{}',
                    error TEXT, created REAL NOT NULL, updated REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    state TEXT NOT NULL, stage TEXT NOT NULL, progress REAL DEFAULT 0,
                    corrections TEXT NOT NULL, cancel_requested INTEGER DEFAULT 0,
                    lease_owner TEXT, lease_until REAL, error TEXT,
                    created REAL NOT NULL, updated REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS job_queue ON jobs(state, created);
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.db_path, timeout=20, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=20000")
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def directory(self, project_id):
        return self.root / valid_id(project_id)

    def revision_directory(self, project_id, revision):
        if not isinstance(revision, int) or revision < 1 or revision > 1_000_000:
            raise StoreError(422, "Invalid project revision.")
        return self.directory(project_id) / "revisions" / str(revision)

    def _capacity(self, db):
        count = db.execute("SELECT COUNT(*) FROM jobs WHERE state IN ('queued','running')").fetchone()[0]
        if count >= self.max_queue:
            raise StoreError(429, "The reconstruction queue is full. Wait for an existing project to finish.")

    def _insert_job(self, db, project_id, revision, corrections, now):
        job_id = str(uuid.uuid4())
        db.execute("INSERT INTO jobs(id,project_id,revision,state,stage,corrections,created,updated) VALUES(?,?,?,'queued','queued',?,?,?)", (job_id, project_id, revision, json.dumps(corrections), now, now))
        return job_id

    def create(self, source: bytes, name: str):
        project_id, now = str(uuid.uuid4()), time.time()
        directory = self.directory(project_id)
        directory.mkdir()
        try:
            (directory / "source.jpg").write_bytes(source)
            with self.transaction() as db:
                self._capacity(db)
                job_id = self._insert_job(db, project_id, 1, {}, now)
                db.execute("INSERT INTO projects(id,name,state,stage,revision,active_job,created,updated) VALUES(?,?,'queued','queued',1,?,?,?)", (project_id, name[:120], job_id, now, now))
        except BaseException:
            shutil.rmtree(directory)
            raise
        return self.get(project_id)

    def rebuild(self, project_id, corrections):
        valid_id(project_id)
        with self.transaction() as db:
            row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
            if row is None:
                raise StoreError(404, "Project not found.")
            if row["state"] in ("queued", "running"):
                raise StoreError(409, "This project already has an active reconstruction.")
            self._capacity(db)
            merged = json.loads(row["corrections"])
            for key, value in corrections.items():
                if isinstance(value, dict) and isinstance(merged.get(key), dict):
                    merged[key] = {**merged[key], **value}
                else:
                    merged[key] = value
            revision, now = row["revision"] + 1, time.time()
            job_id = self._insert_job(db, project_id, revision, merged, now)
            db.execute("UPDATE projects SET state='queued',stage='queued',progress=0,revision=?,active_job=?,corrections=?,error=NULL,updated=? WHERE id=?", (revision, job_id, json.dumps(merged), now, project_id))
        return self.get(project_id)

    def list(self):
        with self.connection() as db:
            rows = db.execute("SELECT * FROM projects ORDER BY created DESC LIMIT 250").fetchall()
        return [self._summary(row) for row in rows]

    def _summary(self, row):
        return {"id": row["id"], "name": row["name"], "state": row["state"], "stage": row["stage"], "progress": row["progress"], "revision": row["revision"], "completedRevision": row["completed_revision"], "jobId": row["active_job"], "createdAt": row["created"], "updatedAt": row["updated"], "error": row["error"]}

    def get(self, project_id):
        valid_id(project_id)
        with self.connection() as db:
            row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if row is None:
            raise StoreError(404, "Project not found.")
        result = self._summary(row)
        result["corrections"] = json.loads(row["corrections"])
        result["warnings"] = []
        display_revision = row["completed_revision"] or row["revision"]
        scene = self.revision_directory(project_id, display_revision) / "scene.json"
        if scene.is_file() and scene.stat().st_size < 4 * 1024 * 1024:
            try:
                result["scene"] = json.loads(scene.read_text())
                result["warnings"] = result["scene"].get("analysis", {}).get("warnings", result["scene"].get("warnings", []))
            except (OSError, ValueError, AttributeError):
                pass
        result["artifacts"] = {"source": f"/api/projects/{project_id}/assets/source"}
        if row["completed_revision"]:
            for asset in ("preview", "glb", "blend", "scene", "manifest"):
                result["artifacts"][asset] = f"/api/projects/{project_id}/assets/{asset}?revision={row['completed_revision']}"
        return result

    def lease_next(self, owner, lease_seconds=45):
        now = time.time()
        with self.transaction() as db:
            db.execute("UPDATE jobs SET state='queued',stage='queued',lease_owner=NULL,lease_until=NULL WHERE state='running' AND (lease_until IS NULL OR lease_until < ?)", (now,))
            if db.execute("SELECT 1 FROM jobs WHERE state='running' LIMIT 1").fetchone():
                return None
            row = db.execute("SELECT * FROM jobs WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
            if row is None:
                return None
            db.execute("UPDATE jobs SET state='running',stage='analyzing',lease_owner=?,lease_until=?,updated=? WHERE id=?", (owner, now + lease_seconds, now, row["id"]))
            db.execute("UPDATE projects SET state='running',stage='analyzing',progress=1,updated=? WHERE id=?", (now, row["project_id"]))
            result = dict(row)
            result["corrections"] = json.loads(result["corrections"])
            return result

    def heartbeat(self, job_id, owner, lease_seconds=45):
        with self.connection() as db:
            db.execute("UPDATE jobs SET lease_until=? WHERE id=? AND lease_owner=? AND state='running'", (time.time() + lease_seconds, job_id, owner))

    def requeue(self, job):
        with self.transaction() as db:
            db.execute("UPDATE jobs SET state='queued',stage='queued',progress=0,lease_owner=NULL,lease_until=NULL,updated=? WHERE id=?", (time.time(), job["id"]))
            db.execute("UPDATE projects SET state='queued',stage='queued',progress=0,updated=? WHERE active_job=?", (time.time(), job["id"]))

    def progress(self, job_id, stage, progress):
        now, progress = time.time(), max(0, min(99, float(progress)))
        with self.transaction() as db:
            db.execute("UPDATE jobs SET stage=?,progress=?,updated=? WHERE id=? AND state='running'", (stage, progress, now, job_id))
            db.execute("UPDATE projects SET stage=?,progress=?,updated=? WHERE active_job=? AND state='running'", (stage, progress, now, job_id))

    def is_cancelled(self, job_id):
        with self.connection() as db:
            row = db.execute("SELECT cancel_requested FROM jobs WHERE id=?", (job_id,)).fetchone()
        return row is None or bool(row[0])

    def cancel(self, project_id):
        valid_id(project_id)
        with self.transaction() as db:
            row = db.execute("SELECT active_job,state FROM projects WHERE id=?", (project_id,)).fetchone()
            if row is None:
                raise StoreError(404, "Project not found.")
            if row["state"] in ("queued", "running"):
                db.execute("UPDATE jobs SET cancel_requested=1 WHERE id=?", (row["active_job"],))
                if row["state"] == "queued":
                    db.execute("UPDATE jobs SET state='cancelled',stage='cancelled',updated=? WHERE id=?", (time.time(), row["active_job"]))
                    db.execute("UPDATE projects SET state='cancelled',stage='cancelled',updated=? WHERE id=?", (time.time(), project_id))
                else:
                    db.execute("UPDATE projects SET stage='cancelling',updated=? WHERE id=?", (time.time(), project_id))
        return self.get(project_id)

    def finish(self, job, state, error=None):
        if state not in ("completed", "failed", "cancelled"):
            raise ValueError("Invalid terminal state")
        now, error = time.time(), str(error)[:800] if error else None
        with self.transaction() as db:
            db.execute("UPDATE jobs SET state=?,stage=?,progress=?,error=?,lease_owner=NULL,lease_until=NULL,updated=? WHERE id=?", (state, state, 100 if state == "completed" else 0, error, now, job["id"]))
            if state == "completed":
                db.execute("UPDATE projects SET state=?,stage=?,progress=100,error=NULL,completed_revision=?,updated=? WHERE active_job=?", (state, state, job["revision"], now, job["id"]))
            else:
                db.execute("UPDATE projects SET state=?,stage=?,progress=0,error=?,updated=? WHERE active_job=?", (state, state, error, now, job["id"]))

    def asset(self, project_id, name, revision=None):
        project = self.get(project_id)
        if name == "source":
            return self.directory(project_id) / "source.jpg", "image/jpeg", "source.jpg"
        mapping = {"preview": ("preview.png", "image/png"), "glb": ("scene.glb", "model/gltf-binary"), "blend": ("scene.blend", "application/octet-stream"), "scene": ("scene.json", "application/json"), "manifest": ("manifest.json", "application/json")}
        if name not in mapping:
            raise StoreError(404, "Unknown project asset.")
        selected = revision if revision is not None else project["completedRevision"]
        if selected is None or selected > (project["completedRevision"] or 0):
            raise StoreError(404, "This project's validated assets are not ready.")
        # Only revisions with a validation marker may be downloaded.
        directory = self.revision_directory(project_id, selected)
        if not (directory / "validated.json").is_file():
            raise StoreError(404, "This revision has no validated artifacts.")
        filename, media_type = mapping[name]
        path = directory / filename
        if not path.is_file():
            raise StoreError(404, "Project asset not found.")
        return path, media_type, filename
