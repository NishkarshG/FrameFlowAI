"""AI layer: OpenRouter client, Pydantic validation, guards and failure handling.

The HTTP layer is replaced by FakeSession so tests are offline and deterministic.
These scripted replies exist only in tests; the application never hardcodes AI output.
"""
import json

import pytest
import requests

from app.ai import AIError, OpenRouterClient, ai_segment_dialogue, critical_details, extract_json, guard_warnings, optimize_dialogue
from app.models import DialogueLine, Segment, Thresholds
from tests.conftest import FakeResponse, chat_reply

TH = Thresholds()


def S(id, text, start=0, end=2000):
    return Segment(id=id, index=0, line_index=0, character="ADRIAN", text=text, original_text=text,
                   start_ms=start, end_ms=end, timing_source="original")


def test_missing_api_key_raises_unavailable():
    client = OpenRouterClient(api_key="")
    with pytest.raises(AIError) as e:
        optimize_dialogue([S("a", "Hello there, how are you doing today?")], "openrouter/free", TH, client=client)
    assert e.value.kind == "unavailable" and "OPENROUTER_API_KEY" in e.value.message


def test_network_failure_raises_unavailable(make_client):
    client, _ = make_client(exc=requests.exceptions.ConnectionError("dns failure"))
    with pytest.raises(AIError) as e:
        client.chat("openrouter/free", [{"role": "user", "content": "x"}])
    assert e.value.kind == "unavailable" and "Could not reach OpenRouter" in e.value.message


def test_timeout_raises_unavailable(make_client):
    client, _ = make_client(exc=requests.exceptions.Timeout())
    with pytest.raises(AIError) as e:
        client.chat("m", [])
    assert "did not respond" in e.value.message


@pytest.mark.parametrize("status,hint", [(401, "valid"), (404, "model id"), (429, "Rate limited")])
def test_http_errors_are_reported_with_hints(make_client, status, hint):
    client, _ = make_client(FakeResponse(status, {"error": {"message": "nope"}}))
    with pytest.raises(AIError) as e:
        client.chat("m", [])
    assert e.value.kind == "http" and str(status) in e.value.message and hint in e.value.message
    assert e.value.raw_output  # raw body preserved


def test_request_uses_backend_key_and_model(make_client):
    client, session = make_client(chat_reply(json.dumps({"suggestions": [{"id": "a", "suggestion": "Sign by midnight."}]})))
    optimize_dialogue([S("a", "You have until midnight to sign the contract, Maya.")], "some/model:free", TH, client=client)
    call = session.calls[0]
    assert call["url"].endswith("/chat/completions")
    assert call["headers"]["Authorization"] == "Bearer test-key"
    assert call["body"]["model"] == "some/model:free"


def test_optimize_valid_reply_is_validated_and_guarded(make_client):
    original = "Your father borrowed four million dollars from my family eleven years ago."
    reply = "```json\n" + json.dumps({"suggestions": [
        {"id": "a", "suggestion": "Your father owes my family millions.", "rationale": "Shorter.", "preserved_details": ["debt"]},
        {"id": "zzz", "suggestion": "Unknown id"},
    ]}) + "\n```"
    client, _ = make_client(chat_reply(reply))
    out = optimize_dialogue([S("a", original, 0, 3000)], "m", TH, client=client)
    assert out.raw_output == reply  # raw output kept verbatim
    assert out.suggestions["a"]["text"] == "Your father owes my family millions."
    # guard flags dropped plot details ("four", "eleven")
    assert any("four" in w and "eleven" in w for w in out.suggestions["a"]["guard_warnings"])
    assert {"id": "zzz", "reason": "Unknown segment id returned by model."} in out.rejected


def test_optimize_invalid_json_raises_invalid_output(make_client):
    client, _ = make_client(chat_reply("Sure! Here is a shorter version: 'Sign it.'"))
    with pytest.raises(AIError) as e:
        optimize_dialogue([S("a", "You have until midnight to sign it.")], "m", TH, client=client)
    assert e.value.kind == "invalid_output"
    assert e.value.raw_output.startswith("Sure!")


def test_optimize_schema_violation_raises(make_client):
    client, _ = make_client(chat_reply(json.dumps({"suggestions": [{"id": "a", "suggestion": "   "}]})))
    with pytest.raises(AIError) as e:
        optimize_dialogue([S("a", "Something long enough.")], "m", TH, client=client)
    assert e.value.kind == "invalid_output"


def test_guard_detects_dropped_negation_and_names():
    w = guard_warnings("I will never marry Adrian Cole.", "I will marry him.")
    assert any("Negation" in x for x in w)
    assert any("Adrian" in x for x in w)
    assert guard_warnings("You have until midnight to sign, Maya.", "Sign by midnight, Maya.") == []


def test_critical_details():
    d = critical_details("Your father borrowed four million dollars from Adrian Cole. He didn't pay.")
    assert {"four", "million", "Adrian", "Cole", "didn't"} <= set(d)


def test_extract_json_handles_prose_and_fences():
    assert extract_json('Here you go:\n```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('noise {"a": {"b": 2}} trailing') == {"a": {"b": 2}}
    with pytest.raises(ValueError):
        extract_json("no json here")


def _line(text):
    return DialogueLine(index=0, character="LILY", text=text, start_ms=0, end_ms=8000, timing_status="ok", source_line=1)


def test_ai_segment_accepts_exact_word_split(make_client):
    text = "This hospital record proves she was admitted to Saint Agnes three weeks before you ever met her, and the notes are notarised."
    parts = ["This hospital record proves she was admitted to Saint Agnes", "three weeks before you ever met her,", "and the notes are notarised."]
    client, _ = make_client(chat_reply(json.dumps({"lines": [{"id": "0", "segments": parts}]})))
    out = ai_segment_dialogue([_line(text)], "m", TH, client=client)
    assert out.accepted == {0: parts}


def test_ai_segment_rejects_reworded_split(make_client):
    text = "This hospital record proves she was admitted to Saint Agnes three weeks before you ever met her."
    client, _ = make_client(chat_reply(json.dumps({"lines": [{"id": "0", "segments": ["This record proves she was admitted", "weeks before you met her."]}]})))
    out = ai_segment_dialogue([_line(text)], "m", TH, client=client)
    assert out.accepted == {}
    assert "changed the wording" in out.rejected[0]["reason"]
