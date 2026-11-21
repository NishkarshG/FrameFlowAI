import json
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app import config  # noqa: E402
from app.ai import OpenRouterClient  # noqa: E402
from app.db import Database  # noqa: E402

SAMPLE_DIR = BACKEND.parent / "sample_data" / "synthetic"


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Never touch the real DB, raw-output folder, or a real API key during tests."""
    monkeypatch.setattr(config, "RAW_AI_DIR", tmp_path / "raw_ai_outputs")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    yield


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def sample_texts():
    return [(p.name, p.read_text(encoding="utf-8")) for p in sorted(SAMPLE_DIR.glob("*.txt"))]


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text if text is not None else json.dumps(payload)

    def json(self):
        if self._payload is None:
            return json.loads(self.text)
        return self._payload


class FakeSession:
    """Stands in for requests.Session: replays a scripted HTTP response or raises."""

    def __init__(self, response=None, exc=None):
        self.response = response
        self.exc = exc
        self.calls = []

    def post(self, url, headers=None, data=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "body": json.loads(data)})
        if self.exc:
            raise self.exc
        return self.response

    def get(self, url, timeout=None):
        if self.exc:
            raise self.exc
        return self.response


def chat_reply(content: str) -> FakeResponse:
    return FakeResponse(200, {"id": "test", "choices": [{"message": {"role": "assistant", "content": content}}]})


@pytest.fixture
def make_client():
    def _make(response=None, exc=None, api_key="test-key"):
        session = FakeSession(response=response, exc=exc)
        return OpenRouterClient(api_key=api_key, base_url="https://example.invalid/api/v1", session=session), session
    return _make
