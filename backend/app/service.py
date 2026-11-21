"""Application services: glue between processing, AI, and the database.

Kept independent of FastAPI so it can be unit-tested directly.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Optional

from . import config
from .ai import AIError, OpenRouterClient, ai_segment_dialogue, optimize_dialogue
from .db import Database, now_iso
from .models import Segment, SegmentUpdate, SettingsModel, SettingsUpdate, Suggestion, Thresholds
from .processing import (
    DISCLAIMER,
    check_readability,
    format_timestamp,
    generate_csv,
    generate_srt,
    parse_screenplay,
    parse_timestamp,
    reindex,
    segments_for_line,
    split_subtitles,
)

OPTIMIZABLE_CODES = {"too_many_chars", "long_line", "too_many_lines", "reading_speed", "long_sentence", "difficult_words"}
MAX_AI_BATCH = 25


class ServiceError(Exception):
    def __init__(self, status: int, message: str, extra: Optional[dict] = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.extra = extra or {}


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
def get_settings(db: Database) -> SettingsModel:
    return db.get_settings()


def update_settings(db: Database, upd: SettingsUpdate) -> SettingsModel:
    s = db.get_settings()
    if upd.model is not None:
        s.model = upd.model
    if upd.thresholds is not None:
        s.thresholds = upd.thresholds
    db.save_settings(s)
    db.log("settings", f"model={s.model}")
    return s


# --------------------------------------------------------------------------- #
# Upload / projects
# --------------------------------------------------------------------------- #
def decode_upload(filename: str, data: bytes) -> str:
    if not filename.lower().endswith(".txt"):
        raise ServiceError(415, f"'{filename}' is not a .txt file. Only plain-text screenplays are supported.")
    if len(data) == 0:
        raise ServiceError(422, f"'{filename}' is empty.")
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise ServiceError(413, f"'{filename}' is larger than {config.MAX_UPLOAD_BYTES // 1024} KB.")
    if b"\x00" in data[:4096]:
        raise ServiceError(415, f"'{filename}' looks like a binary file, not plain text.")
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ServiceError(415, f"Could not decode '{filename}' as text.")


def create_project_from_texts(db: Database, name: str, files: list[tuple[str, str]], force_synthetic: bool = False) -> dict:
    if not files:
        raise ServiceError(422, "Upload at least one .txt screenplay.")
    th = db.get_settings().thresholds
    natural = lambda name: [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]
    files = sorted(files, key=lambda f: natural(f[0]))
    parsed_all = []
    for filename, text in files:
        episodes = parse_screenplay(text, filename)
        parsed_all.append((filename, episodes))
    if not any(ep.dialogue for _, eps in parsed_all for ep in eps):
        raise ServiceError(422, "No dialogue was found. Expected lines such as "
                                "'[00:00:01,000 --> 00:00:03,000] MAYA: Hello' or a CHARACTER cue followed by dialogue.")
    is_synth = force_synthetic or all(ep.is_synthetic for _, eps in parsed_all for ep in eps)
    project = db.create_project(name.strip() or "Untitled project", is_synth)
    pos = 0
    for filename, episodes in parsed_all:
        for ep in episodes:
            segments = split_subtitles(ep.dialogue, th)
            eid = db.create_episode(project["id"], ep.title, filename, pos, ep.is_synthetic or force_synthetic,
                                    ep.raw_text, ep.dialogue, segments, ep.warnings)
            db.log("episode_processed", f"{ep.title}: {len(ep.dialogue)} lines, {len(segments)} segments", project["id"], eid)
            pos += 1
    db.log("project_created", project["name"], project["id"])
    return project_payload(db, project["id"])


def list_sample_files() -> list[dict]:
    out = []
    if config.SAMPLE_DIR.exists():
        for p in sorted(config.SAMPLE_DIR.glob("*.txt")):
            out.append({"filename": p.name, "content": p.read_text(encoding="utf-8"), "synthetic": True})
    return out


def create_sample_project(db: Database) -> dict:
    files = [(f["filename"], f["content"]) for f in list_sample_files()]
    if not files:
        raise ServiceError(404, f"No sample files found in {config.SAMPLE_DIR}")
    return create_project_from_texts(db, "SYNTHETIC DEMO — Midnight Contract", files, force_synthetic=True)


def _episode_summary(row: dict, th: Thresholds) -> dict:
    segs = Database.segments_of(row)
    rep = check_readability(segs, th)
    return {
        "id": row["id"], "name": row["name"], "filename": row["filename"], "is_synthetic": bool(row["is_synthetic"]),
        "segment_count": len(segs), "dialogue_count": len(json.loads(row["dialogue_json"])),
        "issue_count": rep.error_count + rep.warning_count, "error_count": rep.error_count,
        "average_score": rep.average_score,
        "missing_timing": sum(1 for s in segs if s.start_ms is None or s.end_ms is None),
        "pending_suggestions": sum(1 for s in segs if s.suggestion and s.suggestion.status == "pending"),
        "created_at": row["created_at"], "updated_at": row["updated_at"],
    }


def project_payload(db: Database, pid: str) -> dict:
    p = db.get_project(pid)
    if not p:
        raise ServiceError(404, "Project not found.")
    th = db.get_settings().thresholds
    eps = [_episode_summary(r, th) for r in db.list_episodes(pid)]
    return {**p, "is_synthetic": bool(p["is_synthetic"]), "episodes": eps}


def list_projects(db: Database) -> list[dict]:
    return [project_payload(db, p["id"]) for p in db.list_projects()]


def delete_project(db: Database, pid: str) -> None:
    if not db.delete_project(pid):
        raise ServiceError(404, "Project not found.")
    db.log("project_deleted", pid)


# --------------------------------------------------------------------------- #
# Episodes / segments
# --------------------------------------------------------------------------- #
def _row(db: Database, eid: str) -> dict:
    row = db.get_episode_row(eid)
    if not row:
        raise ServiceError(404, "Episode not found.")
    return row


def episode_payload(db: Database, eid: str) -> dict:
    row = _row(db, eid)
    th = db.get_settings().thresholds
    segs = Database.segments_of(row)
    dialogue = Database.dialogue_of(row)
    rep = check_readability(segs, th)
    project = db.get_project(row["project_id"]) or {}
    return {
        "id": row["id"], "project_id": row["project_id"], "project_name": project.get("name"),
        "name": row["name"], "filename": row["filename"], "is_synthetic": bool(row["is_synthetic"]),
        "raw_text": row["raw_text"], "warnings": json.loads(row["warnings_json"]),
        "characters": sorted({d.character for d in dialogue}),
        "dialogue": [d.model_dump() for d in dialogue],
        "segments": [s.model_dump() for s in segs],
        "report": rep.model_dump(),
        "thresholds": th.model_dump(),
        "created_at": row["created_at"], "updated_at": row["updated_at"],
    }


def _find(segs: list[Segment], sid: str) -> Segment:
    for s in segs:
        if s.id == sid:
            return s
    raise ServiceError(404, "Segment not found.")


def update_segment(db: Database, eid: str, sid: str, upd: SegmentUpdate) -> dict:
    row = _row(db, eid)
    segs = Database.segments_of(row)
    seg = _find(segs, sid)
    if upd.text is not None and upd.text != seg.text:
        seg.text = upd.text
        seg.edited = True
    timing_changed = False
    for field_name in ("start", "end"):
        val = getattr(upd, field_name)
        if val is None:
            continue
        try:
            ms = parse_timestamp(val)
        except ValueError as e:
            raise ServiceError(422, str(e)) from e
        attr = f"{field_name}_ms"
        if getattr(seg, attr) != ms:
            setattr(seg, attr, ms)
            timing_changed = True
    if timing_changed:
        seg.timing_source = "manual" if (seg.start_ms is not None or seg.end_ms is not None) else "missing"
    db.save_segments(eid, segs)
    db.log("segment_edited", f"{seg.character} #{seg.index + 1}", row["project_id"], eid)
    return episode_payload(db, eid)


def resplit_episode(db: Database, eid: str) -> dict:
    row = _row(db, eid)
    th = db.get_settings().thresholds
    segs = split_subtitles(Database.dialogue_of(row), th)
    db.save_segments(eid, segs)
    db.log("resplit", f"{len(segs)} segments", row["project_id"], eid)
    return episode_payload(db, eid)


def suggestion_action(db: Database, eid: str, sid: str, action: str, text: Optional[str] = None) -> dict:
    row = _row(db, eid)
    segs = Database.segments_of(row)
    seg = _find(segs, sid)
    if not seg.suggestion:
        raise ServiceError(409, "This segment has no AI suggestion.")
    if action == "accept":
        new_text = (text or seg.suggestion.text).strip()
        if not new_text:
            raise ServiceError(422, "Accepted text cannot be empty.")
        seg.text = new_text
        seg.edited = True
        seg.suggestion.status = "accepted"
    else:
        seg.suggestion.status = "rejected"
    db.save_segments(eid, segs)
    db.log(f"suggestion_{action}ed", f"{seg.character} #{seg.index + 1}", row["project_id"], eid)
    return episode_payload(db, eid)


# --------------------------------------------------------------------------- #
# AI operations
# --------------------------------------------------------------------------- #
def _ai_failure(db: Database, eid: str, row: dict, kind: str, model: str, err: AIError, request) -> ServiceError:
    run = db.record_ai_run(eid, kind, model, "failed", err.message, request, err.raw_output, None)
    db.log("ai_failed", f"{kind}: {err.message[:120]}", row["project_id"], eid)
    status = 502 if err.kind in ("http", "invalid_output") else 503
    return ServiceError(status, err.message, {"ai_run_id": run["id"], "error_kind": err.kind,
                                              "deterministic_checks": "still available"})


def run_optimize(db: Database, eid: str, segment_ids: Optional[list[str]], model: Optional[str],
                 client: Optional[OpenRouterClient] = None) -> dict:
    row = _row(db, eid)
    settings = db.get_settings()
    model = model or settings.model
    th = settings.thresholds
    segs = Database.segments_of(row)
    rep = check_readability(segs, th)
    if segment_ids:
        targets = [s for s in segs if s.id in set(segment_ids)]
    else:
        targets = [s for s in segs if s.text.strip() and any(i.code in OPTIMIZABLE_CODES for i in rep.segments[s.id].issues)
                   and not (s.suggestion and s.suggestion.status == "accepted")]
    targets = [s for s in targets if s.text.strip()][:MAX_AI_BATCH]
    if not targets:
        raise ServiceError(422, "No segments need optimisation. Select segments manually or adjust thresholds.")
    ctx = {}
    for s in targets:
        before = segs[s.index - 1].text if s.index > 0 else None
        after = segs[s.index + 1].text if s.index + 1 < len(segs) else None
        ctx[s.id] = {"previous_subtitle": before, "next_subtitle": after}
    try:
        out = optimize_dialogue(targets, model, th, client=client, context=ctx)
    except AIError as e:
        raise _ai_failure(db, eid, row, "optimize", model, e, {"segment_ids": [s.id for s in targets]})
    run = db.record_ai_run(eid, "optimize", model, "success", None, out.request_messages, out.raw_output,
                           {"validated": out.parsed, "rejected": out.rejected})
    for s in segs:
        if s.id in out.suggestions:
            d = out.suggestions[s.id]
            s.suggestion = Suggestion(text=d["text"], rationale=d["rationale"], preserved_details=d["preserved_details"],
                                      guard_warnings=d["guard_warnings"], model=model, run_id=run["id"], status="pending")
    db.save_segments(eid, segs)
    db.log("ai_optimize", f"{len(out.suggestions)} suggestions via {model}", row["project_id"], eid)
    payload = episode_payload(db, eid)
    payload["ai_result"] = {"run_id": run["id"], "model": model, "suggested": len(out.suggestions), "rejected": out.rejected}
    return payload


def run_ai_segment(db: Database, eid: str, model: Optional[str], client: Optional[OpenRouterClient] = None) -> dict:
    row = _row(db, eid)
    settings = db.get_settings()
    model = model or settings.model
    th = settings.thresholds
    dialogue = Database.dialogue_of(row)
    long_lines = [d for d in dialogue if len(d.text) > th.max_chars_per_segment][:MAX_AI_BATCH]
    if not long_lines:
        raise ServiceError(422, "No dialogue lines exceed the card limit, so there is nothing to segment.")
    try:
        out = ai_segment_dialogue(long_lines, model, th, client=client)
    except AIError as e:
        raise _ai_failure(db, eid, row, "segment", model, e, {"line_indexes": [d.index for d in long_lines]})
    run = db.record_ai_run(eid, "segment", model, "success", None, out.request_messages, out.raw_output,
                           {"validated": out.parsed, "rejected": out.rejected})
    segs = Database.segments_of(row)
    by_line = {d.index: d for d in dialogue}
    new: list[Segment] = []
    done = set()
    for s in segs:
        if s.line_index in out.accepted:
            if s.line_index not in done:
                new.extend(segments_for_line(by_line[s.line_index], out.accepted[s.line_index], method="ai"))
                done.add(s.line_index)
            continue
        new.append(s)
    db.save_segments(eid, reindex(new))
    db.log("ai_segment", f"{len(out.accepted)} lines re-segmented via {model}", row["project_id"], eid)
    payload = episode_payload(db, eid)
    payload["ai_result"] = {"run_id": run["id"], "model": model, "accepted": len(out.accepted), "rejected": out.rejected}
    return payload


def ai_status() -> dict:
    return {"api_key_configured": bool(config.get_api_key()), "base_url": config.OPENROUTER_BASE_URL}


def list_models(client: Optional[OpenRouterClient] = None) -> list[dict]:
    client = client or OpenRouterClient()
    try:
        data = client.list_models()
    except AIError as e:
        raise ServiceError(503, e.message)
    out = []
    for m in data:
        pricing = m.get("pricing") or {}
        free = str(pricing.get("prompt", "1")) in ("0", "0.0") and str(pricing.get("completion", "1")) in ("0", "0.0")
        out.append({"id": m.get("id"), "name": m.get("name") or m.get("id"), "free": free,
                    "context_length": m.get("context_length")})
    out.sort(key=lambda m: (not m["free"], m["id"] or ""))
    return out


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #
def dashboard(db: Database, days: int = 14) -> dict:
    th = db.get_settings().thresholds
    rows = db.list_episodes()
    total_segments = 0
    issues = errors = 0
    scores: list[int] = []
    breakdown: Counter = Counter()
    buckets = {"90–100": 0, "75–89": 0, "50–74": 0, "0–49": 0}
    missing = 0
    synthetic_eps = 0
    for r in rows:
        segs = Database.segments_of(r)
        rep = check_readability(segs, th)
        total_segments += len(segs)
        issues += rep.error_count + rep.warning_count
        errors += rep.error_count
        breakdown.update(rep.issue_breakdown)
        missing += sum(1 for s in segs if s.start_ms is None or s.end_ms is None)
        synthetic_eps += int(bool(r["is_synthetic"]))
        for sr in rep.segments.values():
            scores.append(sr.score)
            b = "90–100" if sr.score >= 90 else "75–89" if sr.score >= 75 else "50–74" if sr.score >= 50 else "0–49"
            buckets[b] += 1

    runs = db.list_ai_runs(limit=10_000)
    today = datetime.now(timezone.utc).date()
    day_keys = [(today - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
    act = {k: {"date": k, "episodes": 0, "ai_success": 0, "ai_failed": 0, "edits": 0} for k in day_keys}
    for r in rows:
        k = r["created_at"][:10]
        if k in act:
            act[k]["episodes"] += 1
    for run in runs:
        k = run["created_at"][:10]
        if k in act:
            act[k]["ai_success" if run["status"] == "success" else "ai_failed"] += 1
    for a in db.activity(limit=5000):
        k = a["created_at"][:10]
        if k in act and a["kind"] in ("segment_edited", "suggestion_accepted", "suggestion_rejected"):
            act[k]["edits"] += 1

    projects = list_projects(db)[:6]
    recent = []
    for p in projects:
        segs = sum(e["segment_count"] for e in p["episodes"])
        sc = [e["average_score"] for e in p["episodes"] if e["average_score"] is not None]
        recent.append({"id": p["id"], "name": p["name"], "is_synthetic": p["is_synthetic"], "created_at": p["created_at"],
                       "episode_count": len(p["episodes"]), "segment_count": segs,
                       "issue_count": sum(e["issue_count"] for e in p["episodes"]),
                       "average_score": round(sum(sc) / len(sc), 1) if sc else None,
                       "first_episode_id": p["episodes"][0]["id"] if p["episodes"] else None})
    return {
        "total_projects": len(db.list_projects()),
        "total_episodes": len(rows),
        "synthetic_episodes": synthetic_eps,
        "total_segments": total_segments,
        "readability_issues": issues,
        "readability_errors": errors,
        "average_score": round(sum(scores) / len(scores), 1) if scores else None,
        "missing_timing": missing,
        "ai_runs": {"success": sum(1 for r in runs if r["status"] == "success"),
                    "failed": sum(1 for r in runs if r["status"] != "success")},
        "issue_breakdown": dict(breakdown.most_common()),
        "score_distribution": buckets,
        "activity": list(act.values()),
        "recent_projects": recent,
        "thresholds": th.model_dump(),
    }


# --------------------------------------------------------------------------- #
# Exports
# --------------------------------------------------------------------------- #
def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")[:80] or "episode"


def export_srt(db: Database, eid: str) -> tuple[str, str, list[str]]:
    row = _row(db, eid)
    th = db.get_settings().thresholds
    srt, skipped = generate_srt(Database.segments_of(row), th)
    prefix = "SYNTHETIC_" if row["is_synthetic"] else ""
    db.log("export", "srt", row["project_id"], eid)
    return srt, f"{prefix}{_safe(row['name'])}.srt", skipped


def export_csv(db: Database, eid: str) -> tuple[str, str]:
    row = _row(db, eid)
    th = db.get_settings().thresholds
    segs = Database.segments_of(row)
    prefix = "SYNTHETIC_" if row["is_synthetic"] else ""
    db.log("export", "csv", row["project_id"], eid)
    return generate_csv(segs, check_readability(segs, th)), f"{prefix}{_safe(row['name'])}_report.csv"


def export_json(db: Database, eid: str) -> tuple[dict, str]:
    row = _row(db, eid)
    p = episode_payload(db, eid)
    segs = [Segment.model_validate(s) for s in p["segments"]]
    report = {
        "generator": "FrameFlow AI",
        "generated_at": now_iso(),
        "data_origin": "SYNTHETIC SAMPLE — fictional demo data" if p["is_synthetic"] else "User-uploaded screenplay",
        "project": p["project_name"], "episode": p["name"], "source_file": p["filename"],
        "thresholds": p["thresholds"], "disclaimer": DISCLAIMER,
        "summary": {k: v for k, v in p["report"].items() if k != "segments"},
        "parse_warnings": p["warnings"],
        "segments": [
            {**s.model_dump(), "start": format_timestamp(s.start_ms) if s.start_ms is not None else None,
             "end": format_timestamp(s.end_ms) if s.end_ms is not None else None,
             "readability": p["report"]["segments"][s.id]} for s in segs
        ],
        "ai_runs_raw": db.list_ai_runs(eid),
    }
    prefix = "SYNTHETIC_" if row["is_synthetic"] else ""
    db.log("export", "json", row["project_id"], eid)
    return report, f"{prefix}{_safe(row['name'])}_analysis.json"


def export_project_zip(db: Database, pid: str) -> tuple[bytes, str]:
    p = project_payload(db, pid)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for e in p["episodes"]:
            srt, name, _ = export_srt(db, e["id"])
            z.writestr(name, srt)
            csv_text, cname = export_csv(db, e["id"])
            z.writestr(cname, csv_text)
            rep, jname = export_json(db, e["id"])
            z.writestr(jname, json.dumps(rep, ensure_ascii=False, indent=2))
    return buf.getvalue(), f"{'SYNTHETIC_' if p['is_synthetic'] else ''}{_safe(p['name'])}.zip"


def ai_runs(db: Database, eid: Optional[str]) -> list[dict]:
    return db.list_ai_runs(eid)

