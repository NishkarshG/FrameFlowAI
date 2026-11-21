"""FrameFlow AI — FastAPI application.

Run:  uvicorn app.main:app --reload --port 8000   (from the backend/ folder)
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from . import config, service
from .db import Database
from .models import AISegmentRequest, OptimizeRequest, SegmentUpdate, SettingsUpdate, SuggestionAction

app = FastAPI(title="FrameFlow AI", version="1.0.0",
              description="Microdrama subtitle & dialogue optimizer API")
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_credentials=False,
                   allow_methods=["*"], allow_headers=["*"], expose_headers=["Content-Disposition", "X-Skipped-Segments"])

_db: Optional[Database] = None


def get_db() -> Database:
    global _db
    if _db is None:
        _db = Database()
    return _db


def get_ai_client():
    """Dependency hook so tests can inject a fake OpenRouter client."""
    return None


@app.exception_handler(service.ServiceError)
async def _service_error(_: Request, exc: service.ServiceError):
    return JSONResponse(status_code=exc.status, content={"detail": exc.message, **exc.extra})


def _download(content: str | bytes, filename: str, media_type: str, extra: Optional[dict] = None) -> Response:
    headers = {"Content-Disposition": f'attachment; filename="{filename}"', **(extra or {})}
    return Response(content=content, media_type=media_type, headers=headers)


# ----------------------------------------------------------------- meta
@app.get("/api/health")
def health(db: Database = Depends(get_db)):
    return {"status": "ok", "ai": service.ai_status(), "model": db.get_settings().model}


@app.get("/api/settings")
def read_settings(db: Database = Depends(get_db)):
    return {**service.get_settings(db).model_dump(), "ai": service.ai_status()}


@app.put("/api/settings")
def write_settings(body: SettingsUpdate, db: Database = Depends(get_db)):
    return {**service.update_settings(db, body).model_dump(), "ai": service.ai_status()}


@app.get("/api/models")
def models(client=Depends(get_ai_client)):
    return service.list_models(client)


@app.get("/api/dashboard")
def dashboard(db: Database = Depends(get_db)):
    return service.dashboard(db)


# ----------------------------------------------------------------- samples / projects
@app.get("/api/samples")
def samples():
    return service.list_sample_files()


@app.post("/api/projects/sample")
def create_sample(db: Database = Depends(get_db)):
    return service.create_sample_project(db)


@app.post("/api/projects")
async def create_project(name: str = Form("Untitled project"), files: list[UploadFile] = File(...),
                         db: Database = Depends(get_db)):
    texts = []
    for f in files:
        data = await f.read()
        texts.append((f.filename or "screenplay.txt", service.decode_upload(f.filename or "screenplay.txt", data)))
    return service.create_project_from_texts(db, name, texts)


@app.get("/api/projects")
def projects(db: Database = Depends(get_db)):
    return service.list_projects(db)


@app.get("/api/projects/{pid}")
def project(pid: str, db: Database = Depends(get_db)):
    return service.project_payload(db, pid)


@app.delete("/api/projects/{pid}")
def delete_project(pid: str, db: Database = Depends(get_db)):
    service.delete_project(db, pid)
    return {"deleted": pid}


@app.get("/api/projects/{pid}/export/zip")
def export_zip(pid: str, db: Database = Depends(get_db)):
    data, name = service.export_project_zip(db, pid)
    return _download(data, name, "application/zip")


# ----------------------------------------------------------------- episodes
@app.get("/api/episodes/{eid}")
def episode(eid: str, db: Database = Depends(get_db)):
    return service.episode_payload(db, eid)


@app.patch("/api/episodes/{eid}/segments/{sid}")
def edit_segment(eid: str, sid: str, body: SegmentUpdate, db: Database = Depends(get_db)):
    return service.update_segment(db, eid, sid, body)


@app.post("/api/episodes/{eid}/resplit")
def resplit(eid: str, db: Database = Depends(get_db)):
    return service.resplit_episode(db, eid)


@app.post("/api/episodes/{eid}/optimize")
def optimize(eid: str, body: OptimizeRequest, db: Database = Depends(get_db), client=Depends(get_ai_client)):
    return service.run_optimize(db, eid, body.segment_ids, body.model, client)


@app.post("/api/episodes/{eid}/ai-segment")
def ai_segment(eid: str, body: AISegmentRequest, db: Database = Depends(get_db), client=Depends(get_ai_client)):
    return service.run_ai_segment(db, eid, body.model, client)


@app.post("/api/episodes/{eid}/segments/{sid}/suggestion")
def suggestion(eid: str, sid: str, body: SuggestionAction, db: Database = Depends(get_db)):
    return service.suggestion_action(db, eid, sid, body.action, body.text)


@app.get("/api/episodes/{eid}/ai-runs")
def episode_ai_runs(eid: str, db: Database = Depends(get_db)):
    return service.ai_runs(db, eid)


@app.get("/api/ai-runs")
def all_ai_runs(db: Database = Depends(get_db)):
    return service.ai_runs(db, None)


@app.get("/api/episodes/{eid}/export/srt")
def export_srt(eid: str, db: Database = Depends(get_db)):
    srt, name, skipped = service.export_srt(db, eid)
    return _download(srt, name, "application/x-subrip; charset=utf-8", {"X-Skipped-Segments": str(len(skipped))})


@app.get("/api/episodes/{eid}/export/csv")
def export_csv(eid: str, db: Database = Depends(get_db)):
    text, name = service.export_csv(db, eid)
    return _download(text, name, "text/csv; charset=utf-8")


@app.get("/api/episodes/{eid}/export/json")
def export_json(eid: str, db: Database = Depends(get_db)):
    data, name = service.export_json(db, eid)
    return _download(json.dumps(data, ensure_ascii=False, indent=2), name, "application/json")
