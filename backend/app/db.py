"""SQLite persistence (standard library only)."""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from . import config
from .models import DialogueLine, Segment, SettingsModel

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    is_synthetic INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS episodes (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    filename TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    is_synthetic INTEGER NOT NULL DEFAULT 0,
    raw_text TEXT NOT NULL,
    dialogue_json TEXT NOT NULL,
    segments_json TEXT NOT NULL,
    warnings_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ai_runs (
    id TEXT PRIMARY KEY,
    episode_id TEXT,
    kind TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    request_json TEXT,
    raw_output TEXT,
    parsed_json TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    detail TEXT,
    project_id TEXT,
    episode_id TEXT,
    created_at TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex[:12]


class Database:
    def __init__(self, path: Optional[str] = None):
        self.path = path or config.DB_PATH
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ------------------------------------------------------------------ utils
    def _exec(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def _all(self, sql: str, params: tuple = ()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def _one(self, sql: str, params: tuple = ()) -> Optional[dict]:
        rows = self._all(sql, params)
        return rows[0] if rows else None

    # --------------------------------------------------------------- settings
    def get_settings(self) -> SettingsModel:
        row = self._one("SELECT value_json FROM settings WHERE key='app'")
        if not row:
            return SettingsModel(model=config.DEFAULT_MODEL)
        return SettingsModel.model_validate_json(row["value_json"])

    def save_settings(self, s: SettingsModel) -> SettingsModel:
        self._exec("INSERT INTO settings(key, value_json) VALUES('app', ?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json",
                   (s.model_dump_json(),))
        return s

    # --------------------------------------------------------------- projects
    def create_project(self, name: str, is_synthetic: bool) -> dict:
        pid = new_id()
        self._exec("INSERT INTO projects(id, name, is_synthetic, created_at) VALUES(?,?,?,?)",
                   (pid, name, int(is_synthetic), now_iso()))
        return self.get_project(pid)  # type: ignore[return-value]

    def get_project(self, pid: str) -> Optional[dict]:
        return self._one("SELECT * FROM projects WHERE id=?", (pid,))

    def list_projects(self) -> list[dict]:
        return self._all("SELECT * FROM projects ORDER BY created_at DESC, rowid DESC")

    def delete_project(self, pid: str) -> bool:
        eps = [e["id"] for e in self._all("SELECT id FROM episodes WHERE project_id=?", (pid,))]
        for eid in eps:
            self._exec("DELETE FROM ai_runs WHERE episode_id=?", (eid,))
        cur = self._exec("DELETE FROM projects WHERE id=?", (pid,))
        return cur.rowcount > 0

    # --------------------------------------------------------------- episodes
    def create_episode(self, project_id: str, name: str, filename: str, position: int, is_synthetic: bool,
                       raw_text: str, dialogue: list[DialogueLine], segments: list[Segment], warnings: list[str]) -> str:
        eid = new_id()
        ts = now_iso()
        self._exec(
            "INSERT INTO episodes(id, project_id, name, filename, position, is_synthetic, raw_text, dialogue_json, segments_json, warnings_json, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (eid, project_id, name, filename, position, int(is_synthetic), raw_text,
             json.dumps([d.model_dump() for d in dialogue]), json.dumps([s.model_dump() for s in segments]),
             json.dumps(warnings), ts, ts),
        )
        return eid

    def get_episode_row(self, eid: str) -> Optional[dict]:
        return self._one("SELECT * FROM episodes WHERE id=?", (eid,))

    def list_episodes(self, project_id: Optional[str] = None) -> list[dict]:
        if project_id:
            return self._all("SELECT * FROM episodes WHERE project_id=? ORDER BY position, created_at", (project_id,))
        return self._all("SELECT * FROM episodes ORDER BY created_at")

    def save_segments(self, eid: str, segments: list[Segment]) -> None:
        self._exec("UPDATE episodes SET segments_json=?, updated_at=? WHERE id=?",
                   (json.dumps([s.model_dump() for s in segments]), now_iso(), eid))

    @staticmethod
    def segments_of(row: dict) -> list[Segment]:
        return [Segment.model_validate(s) for s in json.loads(row["segments_json"])]

    @staticmethod
    def dialogue_of(row: dict) -> list[DialogueLine]:
        return [DialogueLine.model_validate(d) for d in json.loads(row["dialogue_json"])]

    # ---------------------------------------------------------------- ai runs
    def record_ai_run(self, episode_id: Optional[str], kind: str, model: str, status: str, error: Optional[str],
                      request: Any, raw_output: Optional[str], parsed: Any) -> dict:
        rid = new_id()
        ts = now_iso()
        self._exec(
            "INSERT INTO ai_runs(id, episode_id, kind, model, status, error, request_json, raw_output, parsed_json, created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (rid, episode_id, kind, model, status, error, json.dumps(request, ensure_ascii=False) if request is not None else None,
             raw_output, json.dumps(parsed, ensure_ascii=False) if parsed is not None else None, ts),
        )
        run = {"id": rid, "episode_id": episode_id, "kind": kind, "model": model, "status": status, "error": error,
               "request": request, "raw_output": raw_output, "parsed": parsed, "created_at": ts}
        self._write_raw_file(run)
        return run

    def _write_raw_file(self, run: dict) -> None:
        """Mirror every AI call to raw_ai_outputs/ as an unedited JSON record."""
        try:
            config.RAW_AI_DIR.mkdir(parents=True, exist_ok=True)
            fname = f"{run['created_at'].replace(':', '-')}_{run['kind']}_{run['status']}_{run['id']}.json"
            (config.RAW_AI_DIR / fname).write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def list_ai_runs(self, episode_id: Optional[str] = None, limit: int = 200) -> list[dict]:
        if episode_id:
            rows = self._all("SELECT * FROM ai_runs WHERE episode_id=? ORDER BY created_at DESC, rowid DESC LIMIT ?", (episode_id, limit))
        else:
            rows = self._all("SELECT * FROM ai_runs ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,))
        for r in rows:
            r["request"] = json.loads(r.pop("request_json")) if r.get("request_json") else None
            r["parsed"] = json.loads(r.pop("parsed_json")) if r.get("parsed_json") else None
        return rows

    # --------------------------------------------------------------- activity
    def log(self, kind: str, detail: str, project_id: Optional[str] = None, episode_id: Optional[str] = None) -> None:
        self._exec("INSERT INTO activity(kind, detail, project_id, episode_id, created_at) VALUES(?,?,?,?,?)",
                   (kind, detail, project_id, episode_id, now_iso()))

    def activity(self, limit: int = 500) -> list[dict]:
        return self._all("SELECT * FROM activity ORDER BY id DESC LIMIT ?", (limit,))
