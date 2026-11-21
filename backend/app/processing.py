"""Deterministic screenplay processing for FrameFlow AI.

Public functions (reusable, framework independent):
    parse_screenplay()   -> list[ParsedEpisode]
    extract_dialogue()   -> list[DialogueLine]
    split_subtitles()    -> list[Segment]
    check_readability()  -> ReadabilityReport
    generate_srt()       -> (srt_text, skipped_segment_ids)

AI-backed functions (optimize_dialogue, ai_segment_dialogue) live in ai.py.

Timing rules
------------
* Timestamps are only ever taken from the screenplay or typed by the user.
* When a long line is split into several subtitle cards, the ORIGINAL cue window
  is divided proportionally by character count. Those cards are labelled
  ``timing_source="derived_split"`` so editors can see the timing was derived.
* If a cue has no timestamp, every card from it gets ``timing_source="missing"``
  and must be filled in manually. Nothing is guessed.
"""
from __future__ import annotations

import csv
import io
import re
import uuid
from typing import Iterable, Optional

from .models import (
    DEFAULT_THRESHOLDS,
    DialogueLine,
    Issue,
    ParsedEpisode,
    ReadabilityReport,
    Segment,
    SegmentMetrics,
    SegmentReport,
    Thresholds,
)

DISCLAIMER = (
    "Readability checks use configurable editorial guidelines (characters per line, "
    "reading speed, duration, etc.). They are not universal standards — platforms, "
    "languages and audiences differ. Adjust the thresholds in Settings to match your "
    "house style or distributor spec."
)

# --------------------------------------------------------------------------- #
# Timestamp helpers
# --------------------------------------------------------------------------- #
_TS = r"(?:\d{1,2}:)?\d{1,2}:\d{2}(?:[.,]\d{1,3})?"
_PLACEHOLDER = r"(?:\?\?[:?.,\d]*|--[:\-.,]*|TBD|TBC|XX[:X.,]*|MISSING|N/?A)"
_TS_OR_PH = rf"(?:{_TS}|{_PLACEHOLDER})"
_RANGE_RE = re.compile(
    rf"^\s*\[\s*(?P<start>{_TS_OR_PH})\s*(?:(?:-->|->|–|—|-|to)\s*(?P<end>{_TS_OR_PH})?)?\s*\]\s*(?P<rest>.*)$",
    re.IGNORECASE,
)
_BARE_RANGE_RE = re.compile(
    rf"^\s*(?P<start>{_TS})\s*(?:-->|->|–|—|-|to)\s*(?P<end>{_TS})\s*(?P<rest>.*)$",
    re.IGNORECASE,
)
_TS_PARSE = re.compile(r"^(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?:[.,](\d{1,3}))?$")


def parse_timestamp(value: Optional[str]) -> Optional[int]:
    """Parse 'HH:MM:SS,mmm', 'HH:MM:SS.mmm', 'MM:SS' ... into milliseconds.

    Returns None for empty or placeholder values. Raises ValueError for malformed input.
    """
    if value is None:
        return None
    v = value.strip()
    if not v:
        return None
    if re.fullmatch(_PLACEHOLDER, v, re.IGNORECASE):
        return None
    m = _TS_PARSE.match(v)
    if not m:
        raise ValueError(f"Unrecognised timestamp '{value}'. Use HH:MM:SS,mmm")
    h, mnt, s, ms = m.groups()
    h_i = int(h or 0)
    m_i, s_i = int(mnt), int(s)
    if m_i >= 60 or s_i >= 60:
        raise ValueError(f"Minutes/seconds out of range in '{value}'")
    ms_i = int((ms or "0").ljust(3, "0")[:3])
    return ((h_i * 60 + m_i) * 60 + s_i) * 1000 + ms_i


def format_timestamp(ms: Optional[int], sep: str = ",") -> str:
    """Milliseconds -> 'HH:MM:SS,mmm' (SRT style)."""
    if ms is None:
        return "--:--:--" + sep + "---"
    ms = max(0, int(ms))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, msr = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{msr:03d}"


def _timing_from(start_raw: Optional[str], end_raw: Optional[str]) -> tuple[Optional[int], Optional[int], str]:
    try:
        start = parse_timestamp(start_raw)
    except ValueError:
        start = None
    try:
        end = parse_timestamp(end_raw)
    except ValueError:
        end = None
    if start is None:
        return None, end, "missing"
    if end is None:
        return start, None, "missing_end"
    if end <= start:
        return start, end, "invalid"
    return start, end, "ok"


# --------------------------------------------------------------------------- #
# parse_screenplay / extract_dialogue
# --------------------------------------------------------------------------- #
_EPISODE_RE = re.compile(r"^\s*EPISODE\b\s*[:#\-]?\s*(?P<rest>.*)$", re.IGNORECASE)
_TITLE_RE = re.compile(r"^\s*(?:TITLE|SERIES)\s*:\s*(?P<rest>.+)$", re.IGNORECASE)
_SCENE_RE = re.compile(r"^\s*(?:INT\./EXT\.|INT/EXT|I/E|INT|EXT)[.\s]", re.IGNORECASE)
_TRANSITION_RE = re.compile(r"^\s*[A-Z ]+TO:\s*$|^\s*(?:FADE (?:IN|OUT)|CUT TO BLACK)\.?:?\s*$")
_INLINE_DIALOGUE_RE = re.compile(
    r"^(?P<name>[A-Z][A-Z0-9 .'\-]{0,30}?)\s*(?:\((?P<paren>[^)]*)\))?\s*:\s*(?P<text>.*)$"
)
_CUE_RE = re.compile(r"^(?P<name>[A-Z][A-Z0-9 .'\-]{0,30}?)\s*(?:\((?P<ext>[^)]*)\))?\s*$")
_RESERVED = {"TITLE", "SERIES", "EPISODE", "NOTE", "NOTES", "SCENE", "SOURCE", "WARNING", "FORMAT", "DATA"}
_SYNTHETIC_RE = re.compile(r"\bSYNTHETIC\b", re.IGNORECASE)

# Structured "production script" format, e.g.
#   **JULIANA (Confused, Breathless):**
#   Start: (00:13.50) | End: (00:14.30)
#   "Why?"
_META_HEADER_RE = re.compile(
    r"^\s*(?P<key>EPISODE NUMBER|EPISODE TITLE|EPISODE LOGLINE|EPISODE SUMMARY|LOGLINE|SYNOPSIS|CONTINUITY NOTES|SERIES TITLE)\s*:\s*(?P<rest>.*)$",
    re.IGNORECASE,
)
_BOLD_LABEL_RE = re.compile(r"^\*\*(?P<label>[^*]+?):?\*\*:?\s*(?P<rest>.*)$")
_START_END_RE = re.compile(
    rf"^\s*Start\s*:\s*\(?\s*(?P<start>{_TS_OR_PH})?\s*\)?\s*\|\s*End\s*:\s*\(?\s*(?P<end>{_TS_OR_PH})?\s*\)?\s*$",
    re.IGNORECASE,
)
_SCENE_NUM_RE = re.compile(r"^\s*SCENE\s+\d+\b", re.IGNORECASE)
_SCENE_FIELD_RE = re.compile(r"^\s*Scene heading\s*:\s*(?P<h>.+)$", re.IGNORECASE)
_SCENE_META_RE = re.compile(r"^\s*(?:Scene (?:start|end)|Actions and dialogue)\s*:", re.IGNORECASE)
_MARKER_RE = re.compile(r"^\s*-{2,}.*-{2,}\s*$")
_NON_DIALOGUE_LABELS = {
    "CAMERA", "ACTION", "SOUND FX", "SFX", "SOUND", "MUSIC", "VFX", "TRANSITION", "NOTE", "NOTES",
    "TEXT ON SCREEN", "ON-SCREEN TEXT", "ON SCREEN TEXT", "SUPER", "TITLE CARD", "INSERT", "SHOT", "DESCRIPTION", "B-ROLL",
}


def _strip_quotes(text: str) -> str:
    t = text.strip()
    pairs = [('"', '"'), ("\u201c", "\u201d"), ("'", "'"), ("\u2018", "\u2019")]
    for a, b in pairs:
        if len(t) >= 2 and t.startswith(a) and t.endswith(b):
            return t[1:-1].strip()
    return t


def _clean_name(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip().upper()


def parse_screenplay(text: str, filename: str = "screenplay.txt") -> list[ParsedEpisode]:
    """Parse a TXT screenplay into one or more episodes with extracted dialogue.

    Supported dialogue formats (can be mixed in one file):

      [00:00:01,200 --> 00:00:03,800] MAYA: Who are you?
      [00:00:04.0 - 00:00:09.5] ADRIAN (whispering): Someone who knows.
      00:00:10,000 --> 00:00:12,000 MAYA: Inline without brackets.

      [00:00:12,000 --> 00:00:18,500]
      ADRIAN
      (quietly)
      Block-style dialogue, possibly over
      several lines.

    Missing timing can be written as ``[??:??]``, ``[TBD]``, ``[--:--]`` or simply
    omitted; such lines are kept and flagged as missing.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("﻿")
    lines = text.split("\n")
    is_synthetic = bool(_SYNTHETIC_RE.search(text[:2000]))
    default_title = re.sub(r"\.[^.]+$", "", filename).replace("_", " ").strip() or "Episode"

    # Split into episode chunks on EPISODE headers.
    chunks: list[tuple[Optional[str], int, list[str]]] = []
    series_title: Optional[str] = None
    current_title: Optional[str] = None
    current_start = 1
    current: list[str] = []
    for i, line in enumerate(lines, start=1):
        tm = _TITLE_RE.match(line)
        if tm and series_title is None:
            series_title = tm.group("rest").strip()
        mh = _META_HEADER_RE.match(line)
        if mh and mh.group("key").upper() != "EPISODE NUMBER":
            current.append("")  # metadata (logline, notes): keep line numbering, never parse as dialogue
            continue
        em = _EPISODE_RE.match(line)
        if mh or em:
            if current_title is not None or any(l.strip() for l in current if not _is_meta(l)):
                chunks.append((current_title, current_start, current))
            current_title = _episode_title((mh or em).group("rest"), len(chunks) + 1)
            current_start = i + 1
            current = []
            continue
        current.append(line)
    chunks.append((current_title, current_start, current))
    # Drop empty leading chunk (header only) if a titled episode follows
    chunks = [c for c in chunks if c[0] is not None or any(_has_content(l) for l in c[2])] or chunks[:1]

    episodes: list[ParsedEpisode] = []
    for n, (title, start_line, chunk_lines) in enumerate(chunks, start=1):
        ep_title = title or (default_title if len(chunks) == 1 else f"{default_title} — part {n}")
        dialogue, scenes, warnings = extract_dialogue(chunk_lines, line_offset=start_line)
        episodes.append(
            ParsedEpisode(
                title=ep_title,
                series_title=series_title,
                is_synthetic=is_synthetic,
                raw_text="\n".join(chunk_lines).strip("\n"),
                dialogue=dialogue,
                scenes=scenes,
                warnings=warnings,
            )
        )
    return episodes


def _episode_title(rest: str, fallback_n: int) -> str:
    rest = rest.strip()
    m = re.match(r"^(\d+)\s*[:.\-—–]?\s*(.*)$", rest)
    if m:
        return f"Episode {m.group(1)} — {m.group(2).strip()}" if m.group(2).strip() else f"Episode {m.group(1)}"
    return rest or f"Episode {fallback_n}"


def _is_meta(line: str) -> bool:
    s = line.strip()
    return not s or s.startswith("#") or s.startswith("//") or bool(_TITLE_RE.match(s))


def _has_content(line: str) -> bool:
    return not _is_meta(line)


def extract_dialogue(lines: Iterable[str] | str, line_offset: int = 1) -> tuple[list[DialogueLine], list[str], list[str]]:
    """Extract timestamped dialogue from screenplay lines.

    Returns (dialogue, scene_headings, warnings). Original wording and timestamps are
    preserved exactly; only surrounding whitespace is normalised.
    """
    if isinstance(lines, str):
        lines = lines.replace("\r\n", "\n").split("\n")
    lines = list(lines)

    dialogue: list[DialogueLine] = []
    scenes: list[str] = []
    warnings: list[str] = []
    scene: Optional[str] = None

    pending_timing: Optional[tuple[Optional[int], Optional[int], str, str, int]] = None
    block: Optional[dict] = None  # {"name","paren","text":[], "line", "timing", "quoted"}
    skipping = False  # inside a CAMERA / ACTION / SOUND FX block of the structured format

    def emit(name: str, paren: Optional[str], text: str, line_no: int, timing) -> None:
        text = re.sub(r"\s+", " ", text).strip()
        if timing is None:
            start = end = None
            status, raw = "missing", None
        else:
            start, end, status, raw, _ = timing
        dialogue.append(
            DialogueLine(
                index=len(dialogue),
                character=_clean_name(name),
                parenthetical=(paren or "").strip() or None,
                text=text,
                start_ms=start,
                end_ms=end,
                timing_status=status,  # type: ignore[arg-type]
                timing_raw=raw,
                source_line=line_no,
                scene=scene,
            )
        )
        if status == "missing":
            warnings.append(f"Line {line_no}: {name.strip()} has no timestamp — manual input required.")
        elif status == "missing_end":
            warnings.append(f"Line {line_no}: {name.strip()} has a start time but no end time.")
        elif status == "invalid":
            warnings.append(f"Line {line_no}: end time is not after start time.")

    def flush_block() -> None:
        nonlocal block
        if block is not None:
            text = " ".join(block["text"])
            if block.get("quoted"):
                text = _strip_quotes(text)
            emit(block["name"], block["paren"], text, block["line"], block["timing"])
            block = None

    for i, raw_line in enumerate(lines):
        line_no = i + line_offset
        line = raw_line.rstrip()
        stripped = line.strip()

        if not stripped:
            flush_block()
            skipping = False
            continue
        if stripped.startswith("#") or stripped.startswith("//") or _TITLE_RE.match(stripped):
            continue

        # ---- Structured production-script format ----------------------------
        if _MARKER_RE.match(stripped) or _SCENE_NUM_RE.match(stripped):
            flush_block()
            skipping = False
            continue
        sf = _SCENE_FIELD_RE.match(stripped)
        if sf:
            flush_block()
            skipping = False
            scene = sf.group("h").strip()
            scenes.append(scene)
            continue
        if _SCENE_META_RE.match(stripped):
            continue
        bm = _BOLD_LABEL_RE.match(stripped)
        if bm:
            flush_block()
            label = bm.group("label").strip()
            name = label.split("(")[0].strip()
            if not name or _clean_name(name) in _NON_DIALOGUE_LABELS:
                skipping = True
                pending_timing = None
                continue
            skipping = False
            parens = [p.strip() for p in re.findall(r"\(([^)]*)\)", label) if p.strip()]
            block = {"name": name, "paren": "; ".join(parens) or None, "text": [], "line": line_no,
                     "timing": pending_timing, "quoted": True}
            pending_timing = None
            if bm.group("rest").strip():
                block["text"].append(bm.group("rest").strip())
            continue
        se = _START_END_RE.match(stripped)
        if se:
            if skipping:
                continue
            start, end, status = _timing_from(se.group("start"), se.group("end"))
            timing = (start, end, status, stripped, line_no)
            if block is not None and not block["text"]:
                block["timing"] = timing
            else:
                flush_block()
                pending_timing = timing
            continue
        if skipping:
            continue
        # ---------------------------------------------------------------------

        # Timestamp (with or without inline dialogue)
        rm = _RANGE_RE.match(stripped) or _BARE_RANGE_RE.match(stripped)
        if rm:
            flush_block()
            start, end, status = _timing_from(rm.group("start"), rm.group("end"))
            raw = stripped[: len(stripped) - len(rm.group("rest"))].strip()
            timing = (start, end, status, raw, line_no)
            rest = rm.group("rest").strip()
            if rest:
                im = _INLINE_DIALOGUE_RE.match(rest)
                if im and _clean_name(im.group("name")) not in _RESERVED:
                    emit(im.group("name"), im.group("paren"), im.group("text"), line_no, timing)
                else:
                    warnings.append(f"Line {line_no}: timestamp followed by text without a CHARACTER: prefix — ignored as action.")
                pending_timing = None
            else:
                if pending_timing is not None:
                    warnings.append(f"Line {pending_timing[4]}: timestamp had no dialogue after it.")
                pending_timing = timing
            continue

        if _SCENE_RE.match(stripped):
            flush_block()
            scene = stripped
            scenes.append(stripped)
            continue
        if _TRANSITION_RE.match(stripped):
            flush_block()
            continue

        # Inline dialogue "NAME (paren): text"
        im = _INLINE_DIALOGUE_RE.match(stripped)
        if im and _clean_name(im.group("name")) not in _RESERVED and block is None:
            emit(im.group("name"), im.group("paren"), im.group("text"), line_no, pending_timing)
            pending_timing = None
            continue

        if block is not None:
            # Inside a dialogue block: parenthetical or dialogue text
            if stripped.startswith("(") and stripped.endswith(")") and not block["text"]:
                block["paren"] = stripped[1:-1]
            elif stripped.startswith("(") and stripped.endswith(")"):
                pass  # mid-speech parenthetical: not spoken, skip
            else:
                block["text"].append(stripped)
            continue

        # Character cue (block format)
        cm = _CUE_RE.match(stripped)
        if cm and stripped == stripped.upper() and any(c.isalpha() for c in stripped) and _clean_name(cm.group("name")) not in _RESERVED:
            block = {"name": cm.group("name"), "paren": None, "text": [], "line": line_no, "timing": pending_timing}
            pending_timing = None
            continue

        # Otherwise: action line. A pending timestamp stays pending for the next speech.

    flush_block()
    if pending_timing is not None:
        warnings.append(f"Line {pending_timing[4]}: timestamp had no dialogue after it.")
    return dialogue, scenes, warnings


# --------------------------------------------------------------------------- #
# split_subtitles
# --------------------------------------------------------------------------- #
def wrap_text(text: str, max_chars: int) -> list[str]:
    """Greedy word wrap, then balance two-line results for readability."""
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    cur = ""
    for w in words:
        cand = f"{cur} {w}".strip()
        if len(cand) <= max_chars or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    if len(lines) == 2:  # balance the break point
        best = lines
        best_diff = abs(len(lines[0]) - len(lines[1]))
        for k in range(1, len(words)):
            a, b = " ".join(words[:k]), " ".join(words[k:])
            if len(a) <= max_chars and len(b) <= max_chars and abs(len(a) - len(b)) < best_diff:
                best, best_diff = [a, b], abs(len(a) - len(b))
        lines = best
    return lines


def _word_pack(text: str, max_chars: int) -> list[str]:
    out, cur = [], ""
    for w in text.split():
        cand = f"{cur} {w}".strip()
        if len(cand) <= max_chars or not cur:
            cur = cand
        else:
            out.append(cur)
            cur = w
    if cur:
        out.append(cur)
    return out


def chunk_text(text: str, max_chars: int) -> list[str]:
    """Split text at sentence, then clause, then word boundaries into chunks <= max_chars."""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return [text]
    pieces: list[str] = []
    for sentence in re.split(r"(?<=[.!?…])\s+", text):
        if len(sentence) <= max_chars:
            pieces.append(sentence)
            continue
        for clause in re.split(r"(?<=[,;:—])\s+|\s+(?=—)|\s+-\s+", sentence):
            if len(clause) <= max_chars:
                pieces.append(clause)
            else:
                pieces.extend(_word_pack(clause, max_chars))
    merged: list[str] = []
    for p in pieces:
        if merged and len(merged[-1]) + 1 + len(p) <= max_chars:
            merged[-1] = f"{merged[-1]} {p}"
        else:
            merged.append(p)
    return merged


def distribute_timing(chunks: list[str], start_ms: int, end_ms: int) -> list[tuple[int, int]]:
    """Divide an original cue window across chunks proportionally to character count."""
    total = sum(max(len(c), 1) for c in chunks)
    span = end_ms - start_ms
    out, cursor = [], start_ms
    for i, c in enumerate(chunks):
        if i == len(chunks) - 1:
            nxt = end_ms
        else:
            nxt = cursor + round(span * max(len(c), 1) / total)
        out.append((cursor, nxt))
        cursor = nxt
    return out


def _new_id() -> str:
    return uuid.uuid4().hex[:10]


def segments_for_line(line: DialogueLine, chunks: list[str], method: str = "deterministic") -> list[Segment]:
    sources: list[str]
    if line.timing_status == "ok" and line.start_ms is not None and line.end_ms is not None:
        if len(chunks) == 1:
            timings = [(line.start_ms, line.end_ms)]
            sources = ["original"]
        else:
            timings = distribute_timing(chunks, line.start_ms, line.end_ms)
            sources = ["derived_split"] * len(chunks)
    else:
        # Keep whatever the screenplay provided on the first card; never invent the rest.
        timings = [(None, None)] * len(chunks)
        sources = ["missing"] * len(chunks)
        if line.start_ms is not None or line.end_ms is not None:
            timings[0] = (line.start_ms, line.end_ms)
            sources[0] = "original"
    segs = []
    for c, (s, e), source in zip(chunks, timings, sources):
        segs.append(
            Segment(
                id=_new_id(),
                index=0,
                line_index=line.index,
                character=line.character,
                parenthetical=line.parenthetical,
                text=c,
                original_text=c,
                start_ms=s,
                end_ms=e,
                timing_source=source,  # type: ignore[arg-type]
                source_line=line.source_line,
                split_method=method,  # type: ignore[arg-type]
            )
        )
    return segs


def split_subtitles(dialogue: list[DialogueLine], thresholds: Thresholds = DEFAULT_THRESHOLDS) -> list[Segment]:
    """Divide extracted dialogue into readable subtitle cards (deterministic)."""
    segments: list[Segment] = []
    for line in dialogue:
        chunks = chunk_text(line.text, thresholds.max_chars_per_segment) if line.text.strip() else [""]
        segments.extend(segments_for_line(line, chunks))
    return reindex(segments)


def reindex(segments: list[Segment]) -> list[Segment]:
    for i, s in enumerate(segments):
        s.index = i
    return segments


# --------------------------------------------------------------------------- #
# check_readability
# --------------------------------------------------------------------------- #
def count_syllables(word: str) -> int:
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 0
    groups = re.findall(r"[aeiouy]+", w)
    n = len(groups)
    if w.endswith("e") and not w.endswith(("le", "ee")) and n > 1:
        n -= 1
    return max(n, 1)


def segment_metrics(seg: Segment, th: Thresholds) -> SegmentMetrics:
    lines = wrap_text(seg.text, th.max_chars_per_line)
    chars = len(seg.text)
    duration = None
    cps = None
    if seg.start_ms is not None and seg.end_ms is not None and seg.end_ms > seg.start_ms:
        duration = (seg.end_ms - seg.start_ms) / 1000
        cps = round(chars / duration, 2)
    return SegmentMetrics(
        chars=chars,
        lines=lines,
        line_count=len(lines),
        longest_line=max((len(l) for l in lines), default=0),
        duration_s=round(duration, 3) if duration is not None else None,
        cps=cps,
        words=len(seg.text.split()),
    )


def check_readability(segments: list[Segment], thresholds: Thresholds = DEFAULT_THRESHOLDS) -> ReadabilityReport:
    """Run deterministic readability checks on every subtitle segment."""
    th = thresholds
    reports: dict[str, SegmentReport] = {}
    prev: Optional[Segment] = None
    breakdown: dict[str, int] = {}

    for seg in segments:
        m = segment_metrics(seg, th)
        issues: list[Issue] = []

        if not seg.text.strip():
            issues.append(Issue(code="empty_text", severity="error", message="Empty dialogue segment — nothing to display."))
        if m.chars > th.max_chars_per_segment:
            issues.append(Issue(code="too_many_chars", severity="error",
                                message=f"{m.chars} characters exceeds the {th.max_chars_per_segment}-character card limit.",
                                value=m.chars, threshold=th.max_chars_per_segment))
        if m.longest_line > th.max_chars_per_line:
            issues.append(Issue(code="long_line", severity="warning",
                                message=f"A line has {m.longest_line} characters (guideline {th.max_chars_per_line}).",
                                value=m.longest_line, threshold=th.max_chars_per_line))
        if m.line_count > th.max_lines:
            issues.append(Issue(code="too_many_lines", severity="warning",
                                message=f"Wraps to {m.line_count} lines on screen (guideline {th.max_lines}).",
                                value=m.line_count, threshold=th.max_lines))

        # Timing
        if seg.start_ms is None and seg.end_ms is None:
            issues.append(Issue(code="missing_timing", severity="error",
                                message="No timestamp in the screenplay — enter start and end times manually."))
        elif seg.start_ms is None or seg.end_ms is None:
            issues.append(Issue(code="missing_timing", severity="error",
                                message=f"Missing {'start' if seg.start_ms is None else 'end'} time — enter it manually."))
        elif seg.end_ms <= seg.start_ms:
            issues.append(Issue(code="invalid_timing", severity="error",
                                message="End time is not after start time."))
        else:
            dur = m.duration_s or 0
            if dur < th.min_duration_s:
                issues.append(Issue(code="too_short", severity="warning",
                                    message=f"On screen for {dur:.2f}s (guideline minimum {th.min_duration_s:g}s).",
                                    value=dur, threshold=th.min_duration_s))
            if dur > th.max_duration_s:
                issues.append(Issue(code="too_long_duration", severity="warning",
                                    message=f"On screen for {dur:.2f}s (guideline maximum {th.max_duration_s:g}s).",
                                    value=dur, threshold=th.max_duration_s))
            if m.cps is not None and m.cps > th.max_cps:
                issues.append(Issue(code="reading_speed", severity="error" if m.cps > th.max_cps * 1.25 else "warning",
                                    message=f"Reading speed {m.cps:.1f} chars/sec exceeds {th.max_cps:g} cps.",
                                    value=m.cps, threshold=th.max_cps))

        # Overlap with previous segment (script order)
        if prev is not None and prev.end_ms is not None and seg.start_ms is not None and seg.start_ms < prev.end_ms:
            overlap = (prev.end_ms - seg.start_ms) / 1000
            issues.append(Issue(code="overlap", severity="error",
                                message=f"Starts {overlap:.2f}s before the previous subtitle ends ({prev.character}).",
                                value=round(overlap, 3)))

        # Potentially difficult language (heuristic)
        words = re.findall(r"[A-Za-z][A-Za-z'\-]*", seg.text)
        long_words = [w for w in words if len(w) >= th.long_word_chars or count_syllables(w) >= 5]
        if long_words:
            issues.append(Issue(code="difficult_words", severity="info",
                                message="Potentially difficult words: " + ", ".join(sorted(set(long_words))[:5]) + "."))
        for sentence in re.split(r"(?<=[.!?…])\s+", seg.text):
            wc = len(sentence.split())
            if wc > th.max_words_per_sentence:
                issues.append(Issue(code="long_sentence", severity="info",
                                    message=f"Sentence of {wc} words may be hard to read at a glance (guideline {th.max_words_per_sentence}).",
                                    value=wc, threshold=th.max_words_per_sentence))
                break

        score = 100
        for it in issues:
            score -= {"error": 25, "warning": 10, "info": 4}[it.severity]
        score = max(0, score)
        status = "error" if any(i.severity == "error" for i in issues) else ("warning" if any(i.severity == "warning" for i in issues) else "good")
        for it in issues:
            breakdown[it.code] = breakdown.get(it.code, 0) + 1
        reports[seg.id] = SegmentReport(segment_id=seg.id, metrics=m, issues=issues, score=score, status=status)  # type: ignore[arg-type]
        if seg.end_ms is not None or seg.start_ms is not None:
            prev = seg

    all_issues = [i for r in reports.values() for i in r.issues]
    scores = [r.score for r in reports.values()]
    return ReadabilityReport(
        segments=reports,
        total_segments=len(segments),
        issue_count=len(all_issues),
        error_count=sum(1 for i in all_issues if i.severity == "error"),
        warning_count=sum(1 for i in all_issues if i.severity == "warning"),
        issue_breakdown=breakdown,
        average_score=round(sum(scores) / len(scores), 1) if scores else None,
        disclaimer=DISCLAIMER,
    )


# --------------------------------------------------------------------------- #
# Exports
# --------------------------------------------------------------------------- #
def generate_srt(segments: list[Segment], thresholds: Thresholds = DEFAULT_THRESHOLDS) -> tuple[str, list[str]]:
    """Build an SRT file. Segments without valid timing are skipped (never guessed).

    Returns (srt_text, skipped_segment_ids).
    """
    timed, skipped = [], []
    for s in segments:
        if s.start_ms is None or s.end_ms is None or s.end_ms <= s.start_ms or not s.text.strip():
            skipped.append(s.id)
        else:
            timed.append(s)
    timed.sort(key=lambda s: (s.start_ms, s.index))
    blocks = []
    for n, s in enumerate(timed, start=1):
        body = "\n".join(wrap_text(s.text, thresholds.max_chars_per_line))
        blocks.append(f"{n}\n{format_timestamp(s.start_ms)} --> {format_timestamp(s.end_ms)}\n{body}\n")
    return "\n".join(blocks), skipped


CSV_FIELDS = [
    "index", "character", "start", "end", "duration_s", "chars", "cps", "lines", "score", "status",
    "issues", "text", "original_text", "timing_source", "edited", "ai_suggestion", "suggestion_status", "source_line",
]


def generate_csv(segments: list[Segment], report: ReadabilityReport) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_FIELDS)
    w.writeheader()
    for s in segments:
        r = report.segments[s.id]
        w.writerow({
            "index": s.index + 1,
            "character": s.character,
            "start": format_timestamp(s.start_ms) if s.start_ms is not None else "MISSING",
            "end": format_timestamp(s.end_ms) if s.end_ms is not None else "MISSING",
            "duration_s": r.metrics.duration_s if r.metrics.duration_s is not None else "",
            "chars": r.metrics.chars,
            "cps": r.metrics.cps if r.metrics.cps is not None else "",
            "lines": r.metrics.line_count,
            "score": r.score,
            "status": r.status,
            "issues": "; ".join(f"[{i.severity}] {i.message}" for i in r.issues),
            "text": s.text,
            "original_text": s.original_text,
            "timing_source": s.timing_source,
            "edited": s.edited,
            "ai_suggestion": s.suggestion.text if s.suggestion else "",
            "suggestion_status": s.suggestion.status if s.suggestion else "",
            "source_line": s.source_line,
        })
    return buf.getvalue()
