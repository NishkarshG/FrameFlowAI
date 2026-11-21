"""End-to-end service flows: upload -> edit -> AI (success & failure) -> export -> dashboard."""
import json
import zipfile
import io

import pytest
import requests

from app import service
from app.models import SegmentUpdate, SettingsUpdate, Thresholds
from tests.conftest import FakeResponse, chat_reply


def first_episode(db, project):
    return service.episode_payload(db, project["episodes"][0]["id"])


def test_txt_upload_decoding():
    assert service.decode_upload("a.txt", "MAYA: Hi".encode("utf-8-sig")) == "MAYA: Hi"
    assert service.decode_upload("a.txt", "CAFÉ: Olé".encode("cp1252")) == "CAFÉ: Olé"
    for name, data, code in [("a.pdf", b"x", 415), ("a.txt", b"", 422), ("a.txt", b"\x00\x01bin", 415)]:
        with pytest.raises(service.ServiceError) as e:
            service.decode_upload(name, data)
        assert e.value.status == code


def test_upload_without_dialogue_is_rejected(db):
    with pytest.raises(service.ServiceError) as e:
        service.create_project_from_texts(db, "x", [("notes.txt", "Just some prose with no dialogue.")])
    assert e.value.status == 422


def test_sample_project_is_labelled_synthetic(db):
    p = service.create_sample_project(db)
    assert p["is_synthetic"] is True and p["name"].startswith("SYNTHETIC")
    assert len(p["episodes"]) == 2 and all(e["is_synthetic"] for e in p["episodes"])


def test_real_upload_is_not_marked_synthetic(db):
    p = service.create_project_from_texts(db, "Real", [("ep.txt", "[00:00:01,000 --> 00:00:02,000] ANA: Hola.")])
    assert p["is_synthetic"] is False


def test_multiple_files_create_multiple_episodes(db, sample_texts):
    p = service.create_project_from_texts(db, "Two files", sample_texts)
    assert [e["filename"] for e in p["episodes"]] == [n for n, _ in sample_texts]
    assert p["episodes"][0]["dialogue_count"] == 16 and p["episodes"][1]["dialogue_count"] == 15


def test_manual_timing_fixes_missing_issue(db):
    p = service.create_sample_project(db)
    ep = first_episode(db, p)
    target = next(s for s in ep["segments"] if s["start_ms"] is None)
    codes = [i["code"] for i in ep["report"]["segments"][target["id"]]["issues"]]
    assert "missing_timing" in codes
    ep2 = service.update_segment(db, ep["id"], target["id"], SegmentUpdate(start="00:00:21,200", end="00:00:23,600"))
    seg = next(s for s in ep2["segments"] if s["id"] == target["id"])
    assert (seg["start_ms"], seg["end_ms"], seg["timing_source"]) == (21200, 23600, "manual")
    assert "missing_timing" not in [i["code"] for i in ep2["report"]["segments"][target["id"]]["issues"]]


def test_text_edit_and_bad_timestamp(db):
    p = service.create_sample_project(db)
    ep = first_episode(db, p)
    sid = ep["segments"][0]["id"]
    ep2 = service.update_segment(db, ep["id"], sid, SegmentUpdate(text="Who are you?!"))
    s = ep2["segments"][0]
    assert s["text"] == "Who are you?!" and s["edited"] and s["original_text"] == "Who are you?"
    with pytest.raises(service.ServiceError) as e:
        service.update_segment(db, ep["id"], sid, SegmentUpdate(start="banana"))
    assert e.value.status == 422


def test_ai_failure_keeps_deterministic_results_and_logs_run(db, make_client):
    p = service.create_sample_project(db)
    ep = first_episode(db, p)
    before = ep["report"]
    client, _ = make_client(exc=requests.exceptions.ConnectionError("offline"))
    with pytest.raises(service.ServiceError) as e:
        service.run_optimize(db, ep["id"], None, None, client)
    assert e.value.status == 503 and "Could not reach OpenRouter" in e.value.message
    assert e.value.extra["deterministic_checks"] == "still available"
    runs = service.ai_runs(db, ep["id"])
    assert runs[0]["status"] == "failed" and runs[0]["kind"] == "optimize"
    after = service.episode_payload(db, ep["id"])
    assert after["report"]["issue_count"] == before["issue_count"]
    assert all(s["suggestion"] is None for s in after["segments"])  # nothing pretended


def test_ai_failure_without_key(db):
    p = service.create_sample_project(db)
    ep = first_episode(db, p)
    with pytest.raises(service.ServiceError) as e:
        service.run_optimize(db, ep["id"], None, None, None)  # real client, no key set (fixture)
    assert e.value.status == 503 and "OPENROUTER_API_KEY" in e.value.message


def test_optimize_accept_reject_flow(db, make_client):
    p = service.create_sample_project(db)
    ep = first_episode(db, p)
    long_seg = next(s for s in ep["segments"] if s["text"].startswith("Then tomorrow morning"))
    other = next(s for s in ep["segments"] if s["text"].startswith("You have until midnight"))
    reply = json.dumps({"suggestions": [
        {"id": long_seg["id"], "suggestion": "Or the papers learn your father forged signatures.", "rationale": "Cuts words."},
        {"id": other["id"], "suggestion": "Sign by midnight.", "rationale": "Shorter."},
    ]})
    client, session = make_client(chat_reply(reply))
    ep2 = service.run_optimize(db, ep["id"], [long_seg["id"], other["id"]], "custom/model", client)
    assert session.calls[0]["body"]["model"] == "custom/model"
    assert ep2["ai_result"]["suggested"] == 2
    s = next(x for x in ep2["segments"] if x["id"] == long_seg["id"])
    assert s["suggestion"]["status"] == "pending" and s["text"].startswith("Then tomorrow morning")  # original untouched
    ep3 = service.suggestion_action(db, ep["id"], long_seg["id"], "accept")
    s = next(x for x in ep3["segments"] if x["id"] == long_seg["id"])
    assert s["text"] == "Or the papers learn your father forged signatures." and s["suggestion"]["status"] == "accepted"
    assert s["original_text"].startswith("Then tomorrow morning")
    ep4 = service.suggestion_action(db, ep["id"], other["id"], "reject")
    o = next(x for x in ep4["segments"] if x["id"] == other["id"])
    assert o["suggestion"]["status"] == "rejected" and o["text"] == other["text"]
    run = service.ai_runs(db, ep["id"])[0]
    assert run["status"] == "success" and run["raw_output"] == reply


def test_ai_segment_replaces_only_verified_lines(db, make_client):
    p = service.create_sample_project(db)
    ep = first_episode(db, p)
    long_line = next(d for d in ep["dialogue"] if d["text"].startswith("Your father borrowed"))
    words = long_line["text"].split()
    parts = [" ".join(words[:12]), " ".join(words[12:24]), " ".join(words[24:])]
    client, _ = make_client(chat_reply(json.dumps({"lines": [{"id": str(long_line["index"]), "segments": parts}]})))
    ep2 = service.run_ai_segment(db, ep["id"], None, client)
    ai_segs = [s for s in ep2["segments"] if s["split_method"] == "ai"]
    assert [s["text"] for s in ai_segs] == parts
    assert ai_segs[0]["start_ms"] == long_line["start_ms"] and ai_segs[-1]["end_ms"] == long_line["end_ms"]
    assert [s["index"] for s in ep2["segments"]] == list(range(len(ep2["segments"])))


def test_exports(db):
    p = service.create_sample_project(db)
    eid = p["episodes"][1]["id"]
    srt, name, skipped = service.export_srt(db, eid)
    assert name.startswith("SYNTHETIC_") and name.endswith(".srt")
    assert len(skipped) == 3  # missing, invalid, start-only
    assert srt.startswith("1\n00:00:00,500 --> 00:00:02,000\nTurn around, child.")
    csv_text, cname = service.export_csv(db, eid)
    assert cname.endswith(".csv") and "MISSING" in csv_text
    rep, jname = service.export_json(db, eid)
    assert rep["data_origin"].startswith("SYNTHETIC") and "not universal standards" in rep["disclaimer"]
    assert len(rep["segments"]) == p["episodes"][1]["segment_count"]
    data, zname = service.export_project_zip(db, p["id"])
    assert len(zipfile.ZipFile(io.BytesIO(data)).namelist()) == 6


def test_dashboard_reflects_real_data(db, make_client):
    empty = service.dashboard(db)
    assert empty["total_episodes"] == 0 and empty["average_score"] is None
    p = service.create_sample_project(db)
    client, _ = make_client(FakeResponse(429, {"error": {"message": "rate limited"}}))
    with pytest.raises(service.ServiceError):
        service.run_optimize(db, p["episodes"][0]["id"], None, None, client)
    d = service.dashboard(db)
    assert d["total_episodes"] == 2 and d["synthetic_episodes"] == 2
    assert d["total_segments"] == sum(e["segment_count"] for e in p["episodes"])
    assert d["readability_issues"] == sum(e["issue_count"] for e in p["episodes"])
    assert d["ai_runs"] == {"success": 0, "failed": 1}
    assert d["activity"][-1]["episodes"] == 2 and d["activity"][-1]["ai_failed"] == 1
    assert sum(d["score_distribution"].values()) == d["total_segments"]


def test_settings_threshold_change_affects_checks(db):
    p = service.create_sample_project(db)
    eid = p["episodes"][0]["id"]
    strict = service.episode_payload(db, eid)["report"]["issue_count"]
    service.update_settings(db, SettingsUpdate(model="meta-llama/llama-3.3-70b-instruct:free",
                                               thresholds=Thresholds(max_cps=40, max_chars_per_line=60)))
    assert db.get_settings().model == "meta-llama/llama-3.3-70b-instruct:free"
    assert service.episode_payload(db, eid)["report"]["issue_count"] < strict
