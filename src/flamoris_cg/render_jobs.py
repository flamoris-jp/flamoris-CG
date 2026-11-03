"""Durable, reconnectable CG job authority over the existing Flamenco scheduler.

Only admission, idempotency, ownership, reconciliation and result verification
live here. Flamenco owns execution, scheduling and reaping Blender processes.
No daemon, thread, shell, Popen, automatic POST replay or background poll loop.
"""
import contextlib
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import struct
import sys
import time
from uuid import UUID, uuid4
import zipfile

from .flamenco import Flamenco, BackendUnavailable, SubmissionRejected
from .data_contract import canonical, fields

TERMINAL = {"succeeded", "failed", "canceled"}
STATUS = {"completed": "succeeded", "failed": "failed", "canceled": "canceled",
          "queued": "queued", "active": "running", "cancel-requested": "canceling",
          "paused": "paused", "pause-requested": "paused", "requeueing": "queued",
          "under-construction": "queued"}
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def checked_id(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError("invalid managed ID")
    return value


def checked_uuid(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError("canonical UUID required")
    return value


def integer(value, lo, hi):
    if type(value) is not int or not lo <= value <= hi:
        raise ValueError("integer out of range")


def contained(root, path):
    """Trusted owner roots; reject symlink components, including existing parents."""
    root, path = Path(root).absolute(), Path(path).absolute()
    if not path.is_relative_to(root):
        raise ValueError("path outside managed root")
    for component in (path, *path.parents):
        try:
            info = component.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
            raise ValueError("symlinks are not managed artifacts")
    return path


@dataclass(frozen=True)
class JobConfig:
    state_root: Path
    shared_root: Path
    manager_url: str
    max_active: int = 1
    max_jobs: int = 1000
    max_output_bytes: int = 256 * 1024 * 1024
    max_storage_bytes: int = 2 * 1024 * 1024 * 1024
    poll_seconds: int = 30
    timeout_seconds: int = 10
    worker_tag: str | None = None
    retention_seconds: int = 7 * 24 * 3600


class RenderJobs:
    def __init__(self, config, backend=None, clock=time.time):
        self.config, self.clock = config, clock
        integer(config.max_active, 1, 8)
        integer(config.max_jobs, 1, 10000)
        integer(config.poll_seconds, 30, 300)
        integer(config.timeout_seconds, 1, 30)
        integer(config.retention_seconds, 3600, 365 * 24 * 3600)
        integer(config.max_output_bytes, 1024, 4 * 1024**3)
        integer(config.max_storage_bytes, 1024, 100 * 1024**3)
        if config.worker_tag is not None:
            checked_uuid(config.worker_tag)
        self.state = contained(config.state_root, config.state_root)
        self.shared = contained(config.shared_root, config.shared_root)
        self.state.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.shared.mkdir(parents=True, exist_ok=True)
        for name in ("scenes", "jobs"):
            contained(self.shared, self.shared/name).mkdir(exist_ok=True)
        self.backend = backend or Flamenco(config.manager_url, config.timeout_seconds)
        self.db_path = contained(self.state, self.state/"jobs.sqlite3")
        with self.db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS scenes (id TEXT PRIMARY KEY, record TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL, request_hash TEXT NOT NULL, record TEXT NOT NULL)")
            identity = canonical({"manager": config.manager_url.rstrip("/"), "shared_root": str(self.shared)})
            old = db.execute("SELECT value FROM config WHERE key='identity'").fetchone()
            if old and old[0] != identity:
                raise ValueError("state belongs to another Manager or shared root")
            db.execute("INSERT OR IGNORE INTO config VALUES ('identity',?)", (identity,))
            db.execute("INSERT OR IGNORE INTO config VALUES ('namespace',?)", (str(uuid4()),))
            self.namespace = db.execute("SELECT value FROM config WHERE key='namespace'").fetchone()[0]

    @contextlib.contextmanager
    def db(self):
        contained(self.state, self.db_path)
        db = sqlite3.connect(self.db_path, timeout=15)
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _quota(self, reserved=0):
        size = 0
        for directory, subdirs, files in os.walk(self.shared, followlinks=False):
            for name in subdirs + files:
                path = contained(self.shared, Path(directory)/name)
                if path.is_file():
                    size += path.stat().st_size
                if size + reserved > self.config.max_storage_bytes:
                    raise ValueError("managed storage quota exceeded")

    def register_scene(self, scene_id, source, metadata):
        """Trusted local operator only; never expose this as a remote path API.

        The native .blend must be authored/inspected by the operator and have
        packed assets. This is not a sandbox for untrusted .blend files.
        """
        checked_id(scene_id)
        fields(metadata, ("scene_name", "width", "height", "fps", "frame_start", "frame_end"))
        if (not isinstance(metadata["scene_name"], str) or not 1 <= len(metadata["scene_name"]) <= 100
                or any(ord(c) < 32 for c in metadata["scene_name"])):
            raise ValueError("invalid native scene name")
        integer(metadata["width"], 1, 1920)
        integer(metadata["height"], 1, 1080)
        integer(metadata["frame_start"], 1, 1000000)
        integer(metadata["frame_end"], metadata["frame_start"], 1000000)
        fps = metadata["fps"]
        if type(fps) not in (float, int) or not math.isfinite(fps) or not 1 <= fps <= 120:
            raise ValueError("invalid fps")
        source = Path(source)
        if source.suffix.lower() != ".blend" or source.is_symlink() or not source.is_file():
            raise ValueError("trusted native .blend required")
        if not 12 <= source.stat().st_size <= 128 * 1024 * 1024:
            raise ValueError("native size limit")
        record = {**metadata, "sha256": digest(source), "registered_at": self.clock()}
        directory = contained(self.shared, self.shared/"scenes"/scene_id)
        with self.db() as db:
            if db.execute("SELECT 1 FROM scenes WHERE id=?", (scene_id,)).fetchone():
                raise ValueError("scene ID already registered; use a new revision ID")
            self._quota(source.stat().st_size)
            directory.mkdir(exist_ok=False)
            try:
                shutil.copyfile(source, directory/"scene.blend")
                if digest(directory/"scene.blend") != record["sha256"]:
                    raise ValueError("source changed during registration")
                (directory/"scene.json").write_text(canonical(record), encoding="utf-8")
                db.execute("INSERT INTO scenes VALUES (?,?)", (scene_id, canonical(record)))
            except BaseException:
                shutil.rmtree(directory)
                raise
        return {"scene_id": scene_id, **record}

    def _row(self, db, job_id):
        checked_uuid(job_id)
        row = db.execute("SELECT record FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise ValueError("unknown job ID")
        return json.loads(row[0])

    def _save(self, db, record):
        db.execute("UPDATE jobs SET record=? WHERE id=?", (canonical(record), record["job_id"]))

    def _public(self, record):
        terminal = record["status"] in TERMINAL
        return {**record, "terminal": terminal,
                "poll_after_seconds": None if terminal else max(0, math.ceil(record.get("next_poll_at", 0)-self.clock()))}

    def submit(self, request):
        fields(request, ("request_id", "scene_id", "frames"), ("chunk_size",))
        request = {**request, "chunk_size": request.get("chunk_size", 24)}
        checked_uuid(request["request_id"])
        checked_id(request["scene_id"])
        frames = request["frames"]
        if not isinstance(frames, list) or not 1 <= len(frames) <= 240:
            raise ValueError("frames must be an ordered list of 1..240 integers")
        for frame in frames:
            integer(frame, 1, 1000000)
        if frames != sorted(set(frames)):
            raise ValueError("frames must be strictly increasing")
        integer(request["chunk_size"], 1, 240)
        request_hash = hashlib.sha256(canonical(request).encode()).hexdigest()
        with self.db() as db:
            old = db.execute("SELECT request_hash,record FROM jobs WHERE request_id=?", (request["request_id"],)).fetchone()
            if old:
                if old[0] != request_hash:
                    raise ValueError("idempotency key reused for different request")
                return self._public(json.loads(old[1]))
            records = [json.loads(row[0]) for row in db.execute("SELECT record FROM jobs")]
            if len(records) >= 10000 or sum(not r.get("purged") for r in records) >= self.config.max_jobs:
                raise ValueError("job retention limit; explicit terminal cleanup required")
            if sum(r["status"] not in TERMINAL for r in records) >= self.config.max_active:
                raise ValueError("capacity busy; query the existing job before submitting")
            row = db.execute("SELECT record FROM scenes WHERE id=?", (request["scene_id"],)).fetchone()
            if row is None:
                raise ValueError("unknown scene ID")
            scene = json.loads(row[0])
            if frames[0] < scene["frame_start"] or frames[-1] > scene["frame_end"]:
                raise ValueError("frames outside registered native range")
            budget = (scene["width"] * scene["height"] * 4 + 65536) * len(frames)
            if budget > self.config.max_output_bytes:
                raise ValueError("output pixel budget exceeded")
            blend = contained(self.shared, self.shared/"scenes"/request["scene_id"]/"scene.blend")
            if digest(blend) != scene["sha256"]:
                raise ValueError("registered scene changed")
            pending = sum(r.get("reserved_output_bytes", 0) for r in records if r["status"] not in TERMINAL)
            self._quota(budget + pending)
            job_id = str(uuid4())
            root = contained(self.shared, self.shared/"jobs"/job_id)
            root.mkdir(exist_ok=False)
            (root/"frames").mkdir()
            now = self.clock()
            record = {"job_id": job_id, "request": request, "scene": scene,
                      "status": "submitting", "backend_id": None, "created_at": now,
                      "next_poll_at": now+self.config.poll_seconds, "cancel_requested": False,
                      "reserved_output_bytes": budget}
            db.execute("INSERT INTO jobs VALUES (?,?,?,?)", (job_id, request["request_id"], request_hash, canonical(record)))
        # The durable reservation is committed before the only submission POST.
        # A crash here leaves an unknown/submitting reservation, never an auto replay.
        post_attempted = False
        try:
            job_type = self.backend.job_type()
            etag = job_type.get("etag")
            if not isinstance(etag, str) or not 1 <= len(etag) <= 128:
                raise SubmissionRejected("missing_job_type_etag")
            payload = {"name": "CG-"+job_id, "type": "simple-blender-render", "type_etag": etag,
                "priority": 50, "submitter_platform": "windows" if sys.platform == "win32" else sys.platform,
                "metadata": {"project": "FLAMORIS CG", "flamoris.cg.namespace": self.namespace,
                             "flamoris.cg.job_id": job_id, "flamoris.cg.request_id": request["request_id"]},
                "settings": {"blendfile": str(blend), "scene": scene["scene_name"],
                    "frames": ",".join(map(str, frames)), "chunk_size": request["chunk_size"],
                    "fps": scene["fps"], "format": "PNG", "image_file_extension": ".png",
                    "has_previews": False, "add_path_components": 0,
                    "render_output_root": str(root/"frames"), "render_output_path": str(root/"frames"/"######")}}
            if self.config.worker_tag:
                payload["worker_tag"] = self.config.worker_tag
            post_attempted = True
            remote = self.backend.submit(payload)
            with self.db() as db:
                record = self._row(db, job_id)
                self._accept(record, remote)
                self._save(db, record)
        except SubmissionRejected as exc:
            with self.db() as db:
                record = self._row(db, job_id)
                record.update(status="failed", error=str(exc), finished_at=self.clock())
                self._save(db, record)
        except (BackendUnavailable, ValueError, KeyError, TypeError) as exc:
            with self.db() as db:
                record = self._row(db, job_id)
                record.update(status="unknown" if post_attempted else "failed",
                              error=getattr(exc, "code", "submission_outcome_unknown"),
                              next_poll_at=self.clock()+getattr(exc, "retry_after", 60))
                if not post_attempted:
                    record["finished_at"] = self.clock()
                self._save(db, record)
        return self.status(job_id)

    def _accept(self, record, remote):
        metadata = remote.get("metadata", {})
        if metadata.get("flamoris.cg.namespace") != self.namespace or metadata.get("flamoris.cg.job_id") != record["job_id"]:
            raise ValueError("backend ownership mismatch")
        remote_id = checked_uuid(remote["id"])
        if record["backend_id"] and record["backend_id"] != remote_id:
            raise ValueError("backend identity changed")
        record.update(backend_id=remote_id, status=STATUS.get(remote.get("status"), "unknown"),
            backend_status=remote.get("status"), activity=str(remote.get("activity", ""))[:1000],
            steps_completed=remote.get("steps_completed"), steps_total=remote.get("steps_total"),
            backend_created_at=remote.get("created"), backend_updated_at=remote.get("updated"),
            last_checked_at=self.clock(), next_poll_at=self.clock()+self.config.poll_seconds)
        record.pop("error", None)
        if record["status"] in TERMINAL:
            record.setdefault("finished_at", self.clock())

    def status(self, job_id):
        with self.db() as db:
            record = self._row(db, job_id)
            if record["status"] in TERMINAL or self.clock() < record["next_poll_at"]:
                return self._public(record)
            try:
                if record["backend_id"]:
                    remote = self.backend.get(record["backend_id"])
                else:
                    matches = self.backend.find(self.namespace, job_id)
                    if len(matches) != 1:
                        # An absent job after a timeout does not prove rejection.
                        raise BackendUnavailable("submission_requires_reconciliation", 60)
                    remote = matches[0]
                self._accept(record, remote)
            except (BackendUnavailable, ValueError, KeyError, TypeError) as exc:
                record.update(error=getattr(exc, "code", "backend_identity_error"),
                              next_poll_at=self.clock()+getattr(exc, "retry_after", 60))
            self._save(db, record)
            return self._public(record)

    def cancel(self, job_id):
        # Explicit mutation may query once even while ordinary status is cached.
        with self.db() as db:
            record = self._row(db, job_id)
            if record["status"] in TERMINAL or record.get("cancel_acknowledged"):
                return self._public(record)
            if record["cancel_requested"] and self.clock() < record["next_poll_at"]:
                return self._public(record)
            record["cancel_requested"] = True
            self._save(db, record)
        with self.db() as db:
            record = self._row(db, job_id)
            try:
                if not record["backend_id"]:
                    raise BackendUnavailable("reconcile_before_cancel")
                remote = self.backend.get(record["backend_id"])
                self._accept(record, remote)
                if record["status"] not in TERMINAL:
                    self.backend.cancel(record["backend_id"])
                    record.update(cancel_acknowledged=True, status="canceling",
                                  next_poll_at=self.clock()+self.config.poll_seconds)
            except (BackendUnavailable, SubmissionRejected, ValueError, KeyError, TypeError) as exc:
                record.update(error=getattr(exc, "code", "cancel_outcome_unknown"),
                              next_poll_at=self.clock()+getattr(exc, "retry_after", 60))
            self._save(db, record)
            return self._public(record)

    def list_jobs(self, limit=20):
        integer(limit, 1, 100)
        with self.db() as db:
            return [self._public(json.loads(row[0])) for row in
                    db.execute("SELECT record FROM jobs ORDER BY rowid DESC LIMIT ?", (limit,))]

    def result(self, job_id):
        record = self.status(job_id)
        if record.get("purged"):
            return {"job": record, "ready": False, "expired": True}
        if record["status"] not in TERMINAL:
            return {"job": record, "ready": False}
        root = contained(self.shared, self.shared/"jobs"/checked_uuid(job_id))
        bundle = contained(root, root/"result.zip")
        if bundle.exists():
            return {"job": record, "ready": True, "artifact_id": "result.zip",
                    "bytes": bundle.stat().st_size, "sha256": digest(bundle)}
        frames = []
        if record["status"] == "succeeded":
            expected = set(record["request"]["frames"])
            seen = set()
            paths = list((root/"frames").rglob("*.png"))
            if len(paths) > 240:
                raise ValueError("unexpected output count")
            total = 0
            for path in sorted(paths):
                contained(root, path)
                if not re.fullmatch(r"\d{6}\.png", path.name):
                    raise ValueError("unexpected output name")
                frame = int(path.stem)
                if frame not in expected or frame in seen:
                    raise ValueError("unexpected or duplicate frame")
                total += path.stat().st_size
                if total > self.config.max_output_bytes:
                    raise ValueError("output byte limit")
                with path.open("rb") as stream:
                    header = stream.read(24)
                if (header[:16] != b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" or
                        struct.unpack(">II", header[16:24]) != (record["scene"]["width"], record["scene"]["height"])):
                    raise ValueError("output PNG dimensions mismatch")
                frames.append(path)
                seen.add(frame)
            if seen != expected:
                raise ValueError("completed backend has missing frames")
        # Diagnostics belong to this owned backend job only; no arbitrary IDs.
        diagnostics = {}
        if record["backend_id"]:
            try:
                tasks = self.backend.tasks(record["backend_id"])
                diagnostics["tasks"] = tasks
                logs = {}
                task_list = tasks.get("tasks", [])
                task_list = sorted(task_list, key=lambda t: t.get("status") != "failed")
                # One bounded log tail keeps result collection to a small number
                # of backend calls. Full logs remain in Flamenco by backend ID.
                for task in task_list[:1]:
                    logs[checked_uuid(task["id"])] = self.backend.log_tail(task["id"])[-16384:]
                diagnostics["log_tails"] = logs
            except (BackendUnavailable, ValueError, KeyError, TypeError) as exc:
                diagnostics["unavailable"] = getattr(exc, "code", "diagnostics_unavailable")
        self._quota(sum(p.stat().st_size for p in frames)+1024*1024)
        temp = root/(".result-"+str(uuid4())+".zip")
        try:
            with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("job.json", canonical(record))
                archive.writestr("diagnostics.json", canonical(diagnostics))
                for path in frames:
                    archive.write(path, "frames/"+path.name)
            os.replace(temp, bundle)
        finally:
            temp.unlink(missing_ok=True)
        return {"job": record, "ready": True, "artifact_id": "result.zip",
                "bytes": bundle.stat().st_size, "sha256": digest(bundle)}

    def artifact_path(self, job_id):
        """Trusted local transfer only; public requests use job ID + artifact ID."""
        result = self.result(job_id)
        if not result["ready"]:
            raise ValueError("result not ready")
        return contained(self.shared, self.shared/"jobs"/job_id/"result.zip")

    def prune(self, job_id):
        """Explicit local maintenance only; preserve the idempotency tombstone.

        Never runs from status/result. Scenes and other owners' directories are
        not removed. A terminal job must have aged past the retention period.
        """
        with self.db() as db:
            record = self._row(db, job_id)
            if record.get("purged"):
                return self._public(record)
            if record["status"] not in TERMINAL or self.clock()-record["finished_at"] < self.config.retention_seconds:
                raise ValueError("only expired terminal jobs can be pruned")
            root = contained(self.shared, self.shared/"jobs"/checked_uuid(job_id))
            for path in root.rglob("*"):
                contained(root, path)
            if root.exists():
                shutil.rmtree(root)
            record.update(purged=True, purged_at=self.clock())
            self._save(db, record)
            return self._public(record)
