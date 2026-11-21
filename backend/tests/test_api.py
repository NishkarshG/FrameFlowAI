"""HTTP-level tests through FastAPI's TestClient (requires fastapi + httpx)."""
import json

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from app import main  # noqa: E402
from app.db import Database  # noqa: E402
from tests.conftest import chat_reply  # noqa: E402


@pytest.fixture
def client(tmp_path, make_client):
    db = Database(str(tmp_path / "api.db"))
    main.app.dependency_overrides[main.get_db] = lambda: db
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["ai"]["api_key_configured"] is False


def test_upload_txt_and_episode_flow(client):
    files = [("files", ("ep1.txt", b"[00:00:01,000 --> 00:00:02,500] MAYA: Who are you?\nADRIAN: No timing here.", "text/plain"))]
    r = client.post("/api/projects", data={"name": "My show"}, files=files)
    assert r.status_code == 200, r.text
    eid = r.json()["episodes"][0]["id"]
    ep = client.get(f"/api/episodes/{eid}").json()
    assert ep["characters"] == ["ADRIAN", "MAYA"]
    sid = ep["segments"][1]["id"]
    r = client.patch(f"/api/episodes/{eid}/segments/{sid}", json={"start": "00:00:03,000", "end": "00:00:04,500"})
    assert r.status_code == 200 and r.json()["segments"][1]["timing_source"] == "manual"
    srt = client.get(f"/api/episodes/{eid}/export/srt")
    assert srt.status_code == 200 and srt.headers["x-skipped-segments"] == "0"
    assert "attachment" in srt.headers["content-disposition"]
    assert srt.text.startswith("1\n00:00:01,000 --> 00:00:02,500\nWho are you?")
    assert client.get(f"/api/episodes/{eid}/export/csv").status_code == 200
    assert client.get(f"/api/episodes/{eid}/export/json").json()["episode"] == "ep1"


def test_reject_non_txt(client):
    r = client.post("/api/projects", data={"name": "x"}, files=[("files", ("a.pdf", b"%PDF", "application/pdf"))])
    assert r.status_code == 415


def test_optimize_without_key_returns_503_and_checks_still_work(client):
    p = client.post("/api/projects/sample").json()
    eid = p["episodes"][0]["id"]
    r = client.post(f"/api/episodes/{eid}/optimize", json={})
    assert r.status_code == 503
    body = r.json()
    assert "OPENROUTER_API_KEY" in body["detail"] and body["deterministic_checks"] == "still available"
    assert client.get(f"/api/episodes/{eid}").json()["report"]["issue_count"] > 0


def test_optimize_with_injected_client(client, make_client):
    p = client.post("/api/projects/sample").json()
    eid = p["episodes"][0]["id"]
    ep = client.get(f"/api/episodes/{eid}").json()
    sid = next(s["id"] for s in ep["segments"] if s["text"].startswith("Then tomorrow"))
    fake, _ = make_client(chat_reply(json.dumps({"suggestions": [{"id": sid, "suggestion": "Or the press learns he forged signatures."}]})))
    main.app.dependency_overrides[main.get_ai_client] = lambda: fake
    r = client.post(f"/api/episodes/{eid}/optimize", json={"segment_ids": [sid]})
    assert r.status_code == 200 and r.json()["ai_result"]["suggested"] == 1
    r = client.post(f"/api/episodes/{eid}/segments/{sid}/suggestion", json={"action": "accept"})
    assert next(s for s in r.json()["segments"] if s["id"] == sid)["text"] == "Or the press learns he forged signatures."


def test_settings_validation(client):
    assert client.put("/api/settings", json={"model": "has spaces"}).status_code == 422
    assert client.put("/api/settings", json={"thresholds": {"min_duration_s": 9, "max_duration_s": 2}}).status_code == 422
    r = client.put("/api/settings", json={"model": "openrouter/free"})
    assert r.status_code == 200 and r.json()["model"] == "openrouter/free"


def test_dashboard_and_delete(client):
    p = client.post("/api/projects/sample").json()
    d = client.get("/api/dashboard").json()
    assert d["total_episodes"] == 2
    assert client.delete(f"/api/projects/{p['id']}").status_code == 200
    assert client.get("/api/dashboard").json()["total_episodes"] == 0
