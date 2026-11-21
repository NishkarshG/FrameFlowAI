"""Pydantic models shared by the processing pipeline, the AI layer and the API."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

TimingStatus = Literal["ok", "missing", "missing_end", "invalid"]
TimingSource = Literal["original", "derived_split", "manual", "missing"]
Severity = Literal["error", "warning", "info"]
SuggestionStatus = Literal["pending", "accepted", "rejected"]


# --------------------------------------------------------------------------- #
# Configurable editorial thresholds
# --------------------------------------------------------------------------- #
class Thresholds(BaseModel):
    """Editorial guidelines, NOT universal standards. Every value is configurable."""

    max_chars_per_line: int = Field(42, ge=10, le=120)
    max_lines: int = Field(2, ge=1, le=4)
    max_chars_per_segment: int = Field(84, ge=10, le=300)
    max_cps: float = Field(17.0, gt=0, le=60)
    min_duration_s: float = Field(1.0, ge=0, le=10)
    max_duration_s: float = Field(7.0, gt=0, le=30)
    long_word_chars: int = Field(13, ge=6, le=40)
    max_words_per_sentence: int = Field(18, ge=5, le=80)

    @model_validator(mode="after")
    def _check_ranges(self) -> "Thresholds":
        if self.min_duration_s >= self.max_duration_s:
            raise ValueError("min_duration_s must be smaller than max_duration_s")
        return self


DEFAULT_THRESHOLDS = Thresholds()


# --------------------------------------------------------------------------- #
# Parsing output
# --------------------------------------------------------------------------- #
class DialogueLine(BaseModel):
    index: int
    character: str
    parenthetical: Optional[str] = None
    text: str
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None
    timing_status: TimingStatus = "missing"
    timing_raw: Optional[str] = None
    source_line: int  # 1-based line number in the TXT file
    scene: Optional[str] = None


class ParsedEpisode(BaseModel):
    title: str
    series_title: Optional[str] = None
    is_synthetic: bool = False
    raw_text: str
    dialogue: list[DialogueLine] = []
    scenes: list[str] = []
    warnings: list[str] = []


# --------------------------------------------------------------------------- #
# Subtitle segments
# --------------------------------------------------------------------------- #
class Suggestion(BaseModel):
    text: str
    rationale: str = ""
    preserved_details: list[str] = []
    guard_warnings: list[str] = []
    model: str = ""
    run_id: Optional[str] = None
    status: SuggestionStatus = "pending"


class Segment(BaseModel):
    id: str
    index: int
    line_index: int
    character: str
    parenthetical: Optional[str] = None
    text: str
    original_text: str  # the segment text as first produced from the screenplay
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None
    timing_source: TimingSource = "missing"
    source_line: int = 0
    edited: bool = False
    split_method: Literal["deterministic", "ai"] = "deterministic"
    suggestion: Optional[Suggestion] = None


class Issue(BaseModel):
    code: str
    severity: Severity
    message: str
    value: Optional[float] = None
    threshold: Optional[float] = None


class SegmentMetrics(BaseModel):
    chars: int
    lines: list[str]
    line_count: int
    longest_line: int
    duration_s: Optional[float]
    cps: Optional[float]
    words: int


class SegmentReport(BaseModel):
    segment_id: str
    metrics: SegmentMetrics
    issues: list[Issue]
    score: int
    status: Literal["good", "warning", "error"]


class ReadabilityReport(BaseModel):
    segments: dict[str, SegmentReport]
    total_segments: int
    issue_count: int
    error_count: int
    warning_count: int
    issue_breakdown: dict[str, int]
    average_score: Optional[float]
    disclaimer: str


# --------------------------------------------------------------------------- #
# API request bodies
# --------------------------------------------------------------------------- #
class SegmentUpdate(BaseModel):
    text: Optional[str] = None
    start: Optional[str] = None  # "HH:MM:SS,mmm" or "" to clear
    end: Optional[str] = None

    @field_validator("text")
    @classmethod
    def _strip(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if v is not None else v


class SuggestionAction(BaseModel):
    action: Literal["accept", "reject"]
    text: Optional[str] = None  # optional user-tweaked version when accepting


class OptimizeRequest(BaseModel):
    segment_ids: Optional[list[str]] = None  # None -> all segments with issues
    model: Optional[str] = None


class AISegmentRequest(BaseModel):
    model: Optional[str] = None


class SettingsModel(BaseModel):
    model: str = "openrouter/free"
    thresholds: Thresholds = Thresholds()


class SettingsUpdate(BaseModel):
    model: Optional[str] = None
    thresholds: Optional[Thresholds] = None

    @field_validator("model")
    @classmethod
    def _model_ok(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v or len(v) > 200 or " " in v:
            raise ValueError("model must be a non-empty OpenRouter model id without spaces")
        return v


# --------------------------------------------------------------------------- #
# AI response schemas (validated with Pydantic before use)
# --------------------------------------------------------------------------- #
class AISuggestionItem(BaseModel):
    id: str
    suggestion: str
    rationale: str = ""
    preserved_details: list[str] = []

    @field_validator("suggestion")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("suggestion must not be empty")
        return v


class AIOptimizeResponse(BaseModel):
    suggestions: list[AISuggestionItem]


class AISegmentItem(BaseModel):
    id: str
    segments: list[str]

    @field_validator("segments")
    @classmethod
    def _non_empty(cls, v: list[str]) -> list[str]:
        v = [s.strip() for s in v if s and s.strip()]
        if not v:
            raise ValueError("segments must contain at least one non-empty string")
        return v


class AISegmentResponse(BaseModel):
    lines: list[AISegmentItem]
