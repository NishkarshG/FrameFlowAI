"""OpenRouter-backed AI functions: optimize_dialogue() and ai_segment_dialogue().

Design rules
------------
* The API key is read on the backend only (OPENROUTER_API_KEY).
* Every AI response is validated with Pydantic before it is used.
* Raw, unedited model output is always returned to the caller so it can be stored
  and exported — including outputs that failed validation.
* On any failure an AIError is raised; nothing is ever faked or hardcoded.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

import requests
from pydantic import ValidationError

from . import config
from .models import AIOptimizeResponse, AISegmentResponse, DialogueLine, Segment, Thresholds


class AIError(Exception):
    """Raised when AI analysis could not be completed."""

    def __init__(self, message: str, kind: str = "unavailable", raw_output: Optional[str] = None, status_code: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.kind = kind  # unavailable | http | invalid_output
        self.raw_output = raw_output
        self.status_code = status_code


# --------------------------------------------------------------------------- #
# OpenRouter client
# --------------------------------------------------------------------------- #
class OpenRouterClient:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None,
                 timeout: Optional[float] = None, session: Optional[Any] = None):
        self.api_key = api_key if api_key is not None else config.get_api_key()
        self.base_url = (base_url or config.OPENROUTER_BASE_URL).rstrip("/")
        self.timeout = timeout or config.AI_TIMEOUT_S
        self.session = session or requests.Session()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:5173",
            "X-Title": "FrameFlow AI",
        }

    def chat(self, model: str, messages: list[dict[str, str]], temperature: float = 0.3) -> tuple[str, dict]:
        if not self.api_key:
            raise AIError("OPENROUTER_API_KEY is not set on the backend. Add it to backend/.env and restart the server. "
                          "Deterministic readability checks still work.", kind="unavailable")
        payload = {"model": model, "messages": messages, "temperature": temperature}
        try:
            resp = self.session.post(f"{self.base_url}/chat/completions", headers=self._headers(),
                                     data=json.dumps(payload), timeout=self.timeout)
        except requests.exceptions.Timeout as e:
            raise AIError(f"OpenRouter did not respond within {self.timeout:.0f}s.", kind="unavailable") from e
        except requests.exceptions.RequestException as e:
            raise AIError(f"Could not reach OpenRouter: {e.__class__.__name__}: {e}", kind="unavailable") from e

        text = resp.text
        if resp.status_code != 200:
            detail = text[:500]
            try:
                detail = resp.json().get("error", {}).get("message", detail)
            except Exception:
                pass
            hint = {401: " Check that OPENROUTER_API_KEY is valid.", 402: " The account has insufficient credits for this model.",
                    404: " The model id may not exist — pick another model in Settings.", 429: " Rate limited — wait and retry, or switch model."}.get(resp.status_code, "")
            raise AIError(f"OpenRouter returned HTTP {resp.status_code}: {detail}.{hint}", kind="http",
                          raw_output=text, status_code=resp.status_code)
        try:
            data = resp.json()
        except ValueError as e:
            raise AIError("OpenRouter returned a non-JSON response.", kind="http", raw_output=text) from e
        if isinstance(data, dict) and data.get("error"):
            msg = data["error"].get("message", str(data["error"])) if isinstance(data["error"], dict) else str(data["error"])
            raise AIError(f"OpenRouter error: {msg}", kind="http", raw_output=text)
        try:
            content = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as e:
            raise AIError("OpenRouter response did not contain a message.", kind="invalid_output", raw_output=text) from e
        if not content.strip():
            raise AIError("The model returned an empty answer.", kind="invalid_output", raw_output=text)
        return content, data

    def list_models(self) -> list[dict]:
        try:
            resp = self.session.get(f"{self.base_url}/models", timeout=20)
            resp.raise_for_status()
            return resp.json().get("data", [])
        except Exception as e:  # noqa: BLE001
            raise AIError(f"Could not load model list: {e}", kind="unavailable") from e


def extract_json(content: str) -> Any:
    """Extract the first JSON object from a model reply (handles ```json fences)."""
    s = content.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", s, re.DOTALL)
    if fence:
        s = fence.group(1).strip()
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object found in model output")
    return json.loads(s[start:end + 1])


# --------------------------------------------------------------------------- #
# Plot-information guard (deterministic)
# --------------------------------------------------------------------------- #
_NUMBER_WORDS = {"one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
                 "twenty", "thirty", "hundred", "thousand", "million", "billion", "first", "second", "third", "half"}
_NEGATIONS = {"not", "never", "no", "nobody", "nothing", "none", "nowhere", "neither", "nor"}
_STOP_CAPS = {"I", "I'm", "I'll", "I've", "I'd", "OK", "Okay"}


def critical_details(text: str) -> list[str]:
    """Numbers, names/places (mid-sentence capitals), and negations."""
    details: list[str] = []
    for sentence in re.split(r"(?<=[.!?…])\s+", text):
        for pos, tok in enumerate(re.findall(r"[A-Za-z0-9][A-Za-z0-9'\-]*", sentence)):
            low = tok.lower()
            if re.search(r"\d", tok) or low in _NUMBER_WORDS:
                details.append(tok)
            elif tok[0].isupper() and pos > 0 and tok not in _STOP_CAPS:
                details.append(tok)
            elif low in _NEGATIONS or low.endswith("n't"):
                details.append(tok)
    seen, out = set(), []
    for d in details:
        if d.lower() not in seen:
            seen.add(d.lower())
            out.append(d)
    return out


def guard_warnings(original: str, suggestion: str) -> list[str]:
    warnings = []
    sug_low = suggestion.lower()
    missing = [d for d in critical_details(original) if d.lower() not in sug_low]
    neg_missing = [d for d in missing if d.lower() in _NEGATIONS or d.lower().endswith("n't")]
    other_missing = [d for d in missing if d not in neg_missing]
    if other_missing:
        warnings.append("Check plot details — not found in suggestion: " + ", ".join(other_missing))
    if neg_missing:
        orig_neg = sum(1 for t in re.findall(r"[A-Za-z']+", original.lower()) if t in _NEGATIONS or t.endswith("n't"))
        sug_neg = sum(1 for t in re.findall(r"[A-Za-z']+", sug_low) if t in _NEGATIONS or t.endswith("n't"))
        if sug_neg < orig_neg:
            warnings.append("Negation may have been dropped (" + ", ".join(neg_missing) + ") — meaning could flip.")
    if len(suggestion) >= len(original):
        warnings.append("Suggestion is not shorter than the original.")
    return warnings


# --------------------------------------------------------------------------- #
# optimize_dialogue
# --------------------------------------------------------------------------- #
OPTIMIZE_SYSTEM = (
    "You are a senior subtitle editor for short-form vertical microdramas watched on phones. "
    "You shorten subtitle text so it can be read quickly, while: (1) preserving the original meaning, "
    "(2) preserving the emotional tone and the character's voice, (3) NEVER changing or removing plot information "
    "such as names, numbers, places, relationships, threats, promises, secrets or negations. "
    "Do not add new information. Keep the same language as the original. "
    "Reply with ONLY a JSON object, no commentary."
)


@dataclass
class OptimizeOutcome:
    suggestions: dict[str, dict] = field(default_factory=dict)  # segment_id -> {text, rationale, preserved_details, guard_warnings}
    rejected: list[dict] = field(default_factory=list)  # {"id", "reason"}
    raw_output: str = ""
    request_messages: list[dict] = field(default_factory=list)
    parsed: Optional[dict] = None


def build_optimize_messages(items: list[dict], thresholds: Thresholds) -> list[dict[str, str]]:
    user = {
        "task": "Suggest a shorter alternative for each subtitle.",
        "constraints": {
            "target_max_characters": thresholds.max_chars_per_segment,
            "target_reading_speed_cps": thresholds.max_cps,
            "keep_meaning": True, "keep_emotional_tone": True, "keep_plot_information": True,
        },
        "subtitles": items,
        "response_format": {
            "suggestions": [{"id": "<same id as input>", "suggestion": "<shorter subtitle text>",
                             "rationale": "<one short sentence>", "preserved_details": ["<key plot details kept>"]}]
        },
    }
    return [{"role": "system", "content": OPTIMIZE_SYSTEM},
            {"role": "user", "content": json.dumps(user, ensure_ascii=False, indent=1)}]


def optimize_dialogue(segments: list[Segment], model: str, thresholds: Thresholds,
                      client: Optional[OpenRouterClient] = None, context: Optional[dict[str, dict]] = None) -> OptimizeOutcome:
    """Ask the model for shorter alternatives. Raises AIError on any failure."""
    client = client or OpenRouterClient()
    items = []
    for s in segments:
        item = {"id": s.id, "character": s.character, "text": s.text}
        if s.parenthetical:
            item["delivery"] = s.parenthetical
        if s.start_ms is not None and s.end_ms is not None and s.end_ms > s.start_ms:
            dur = (s.end_ms - s.start_ms) / 1000
            item["seconds_on_screen"] = round(dur, 2)
            item["max_characters_for_this_duration"] = int(dur * thresholds.max_cps)
        if context and s.id in context:
            item.update(context[s.id])
        items.append(item)
    messages = build_optimize_messages(items, thresholds)
    content, _ = client.chat(model, messages)
    outcome = OptimizeOutcome(raw_output=content, request_messages=messages)
    try:
        parsed = AIOptimizeResponse.model_validate(extract_json(content))
    except (ValueError, ValidationError) as e:
        raise AIError(f"The model's reply was not valid JSON for the expected schema: {str(e)[:300]}",
                      kind="invalid_output", raw_output=content) from e
    outcome.parsed = parsed.model_dump()
    by_id = {s.id: s for s in segments}
    for item in parsed.suggestions:
        seg = by_id.get(item.id)
        if seg is None:
            outcome.rejected.append({"id": item.id, "reason": "Unknown segment id returned by model."})
            continue
        if item.suggestion.strip() == seg.text.strip():
            outcome.rejected.append({"id": item.id, "reason": "Suggestion identical to original."})
            continue
        outcome.suggestions[item.id] = {
            "text": item.suggestion,
            "rationale": item.rationale,
            "preserved_details": item.preserved_details,
            "guard_warnings": guard_warnings(seg.text, item.suggestion),
        }
    for s in segments:
        if s.id not in outcome.suggestions and not any(r["id"] == s.id for r in outcome.rejected):
            outcome.rejected.append({"id": s.id, "reason": "Model returned no suggestion for this segment."})
    return outcome


# --------------------------------------------------------------------------- #
# ai_segment_dialogue
# --------------------------------------------------------------------------- #
SEGMENT_SYSTEM = (
    "You are a subtitle editor for vertical microdramas. Split each dialogue line into subtitle cards at natural "
    "speech pauses (sentence ends, clause boundaries, breaths). Use the EXACT original words in the exact order — "
    "do not rewrite, add, remove or reorder any word. Each card should be at most the given character limit. "
    "Reply with ONLY a JSON object, no commentary."
)


def _norm_words(s: str) -> list[str]:
    return re.sub(r"\s+", " ", s).strip().split(" ")


@dataclass
class SegmentOutcome:
    accepted: dict[int, list[str]] = field(default_factory=dict)  # line_index -> chunks
    rejected: list[dict] = field(default_factory=list)
    raw_output: str = ""
    request_messages: list[dict] = field(default_factory=list)
    parsed: Optional[dict] = None


def ai_segment_dialogue(lines: list[DialogueLine], model: str, thresholds: Thresholds,
                        client: Optional[OpenRouterClient] = None) -> SegmentOutcome:
    """Ask the model where to split long lines. Every split is verified word-for-word."""
    client = client or OpenRouterClient()
    items = [{"id": str(l.index), "character": l.character, "text": l.text} for l in lines]
    user = {
        "task": "Split each line into subtitle cards.",
        "max_characters_per_card": thresholds.max_chars_per_segment,
        "lines": items,
        "response_format": {"lines": [{"id": "<same id>", "segments": ["<card 1 text>", "<card 2 text>"]}]},
    }
    messages = [{"role": "system", "content": SEGMENT_SYSTEM},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False, indent=1)}]
    content, _ = client.chat(model, messages, temperature=0.1)
    outcome = SegmentOutcome(raw_output=content, request_messages=messages)
    try:
        parsed = AISegmentResponse.model_validate(extract_json(content))
    except (ValueError, ValidationError) as e:
        raise AIError(f"The model's reply was not valid JSON for the expected schema: {str(e)[:300]}",
                      kind="invalid_output", raw_output=content) from e
    outcome.parsed = parsed.model_dump()
    by_idx = {str(l.index): l for l in lines}
    for item in parsed.lines:
        line = by_idx.get(item.id)
        if line is None:
            outcome.rejected.append({"id": item.id, "reason": "Unknown line id returned by model."})
            continue
        if _norm_words(" ".join(item.segments)) != _norm_words(line.text):
            outcome.rejected.append({"id": item.id, "reason": "Model changed the wording — kept deterministic split."})
            continue
        too_long = [c for c in item.segments if len(c) > thresholds.max_chars_per_segment]
        if too_long:
            outcome.rejected.append({"id": item.id, "reason": "A card exceeded the character limit — kept deterministic split."})
            continue
        outcome.accepted[line.index] = item.segments
    return outcome
