"""Deterministic pipeline: extraction, splitting, readability and SRT."""
import pytest

from app.models import Segment, Thresholds
from app.processing import (
    check_readability,
    chunk_text,
    extract_dialogue,
    format_timestamp,
    generate_csv,
    generate_srt,
    parse_screenplay,
    parse_timestamp,
    split_subtitles,
    wrap_text,
)


def seg(id, text, start, end, idx=0, char="A"):
    return Segment(id=id, index=idx, line_index=idx, character=char, text=text, original_text=text,
                   start_ms=start, end_ms=end, timing_source="original")


# ------------------------------------------------------------------ timestamps
@pytest.mark.parametrize("raw,ms", [
    ("00:00:01,000", 1000), ("00:00:01.5", 1500), ("01:02:03,004", 3723004), ("02:05", 125000), ("0:00:00,07", 70),
])
def test_parse_timestamp(raw, ms):
    assert parse_timestamp(raw) == ms


@pytest.mark.parametrize("raw", ["", "??:??", "TBD", "--:--"])
def test_placeholders_mean_missing(raw):
    assert parse_timestamp(raw) is None


@pytest.mark.parametrize("raw", ["1:2", "00:61:00", "abc", "00:00:99"])
def test_bad_timestamps_raise(raw):
    with pytest.raises(ValueError):
        parse_timestamp(raw)


def test_format_timestamp_roundtrip():
    assert format_timestamp(3723004) == "01:02:03,004"
    assert parse_timestamp(format_timestamp(987654)) == 987654


# ------------------------------------------------------------------ extraction
def test_sample_episode_1_extraction(sample_texts):
    name, text = sample_texts[0]
    eps = parse_screenplay(text, name)
    assert len(eps) == 1
    ep = eps[0]
    assert ep.is_synthetic is True
    assert ep.title == "Episode 1 — The Contract"
    assert len(ep.dialogue) == 16
    first = ep.dialogue[0]
    assert (first.character, first.text, first.start_ms, first.end_ms) == ("MAYA", "Who are you?", 1000, 2600)
    # parenthetical captured, block-format text joined without altering words
    block = ep.dialogue[2]
    assert block.character == "ADRIAN" and block.parenthetical == "turning slowly"
    assert block.text.startswith("Your father borrowed four million dollars") and block.text.endswith("eldest Cole son.")


def test_character_identification(sample_texts):
    chars = set()
    for name, text in sample_texts:
        for ep in parse_screenplay(text, name):
            chars |= {d.character for d in ep.dialogue}
    assert chars == {"MAYA", "ADRIAN", "LILY", "GRANDMA COLE", "OFFICIANT"}


def test_missing_invalid_and_partial_timing_flagged(sample_texts):
    ep2 = parse_screenplay(sample_texts[1][1], sample_texts[1][0])[0]
    by_text = {d.text: d for d in ep2.dialogue}
    assert by_text["Then you're braver than he is."].timing_status == "missing"
    assert by_text["I do."].timing_status == "invalid"
    assert by_text["Lily, get out."].timing_status == "missing_end"
    assert by_text["Lily, get out."].start_ms == 28500
    assert any("no timestamp" in w for w in ep2.warnings)


def test_multiple_episodes_in_one_file():
    text = "EPISODE 1: Pilot\n[00:00:01,000 --> 00:00:02,000] A: Hi.\nEPISODE 2: Next\n[00:00:01,000 --> 00:00:02,000] B: Bye."
    eps = parse_screenplay(text, "two.txt")
    assert [e.title for e in eps] == ["Episode 1 — Pilot", "Episode 2 — Next"]
    assert [e.dialogue[0].character for e in eps] == ["A", "B"]


def test_scene_headings_and_actions_not_dialogue():
    lines = ["INT. CAFE - DAY", "Rain falls. Nobody speaks.", "", "[00:00:01,000 --> 00:00:02,000]", "BOB", "Hello there.", "", "CUT TO:"]
    dialogue, scenes, _ = extract_dialogue(lines)
    assert scenes == ["INT. CAFE - DAY"]
    assert len(dialogue) == 1 and dialogue[0].character == "BOB" and dialogue[0].scene == "INT. CAFE - DAY"


def test_no_timestamps_are_invented():
    dialogue, _, _ = extract_dialogue(["ANNA: I have no timing at all, and this line is long enough to be split into more than one card for sure."])
    segs = split_subtitles(dialogue, Thresholds(max_chars_per_segment=40))
    assert len(segs) > 1
    assert all(s.start_ms is None and s.end_ms is None and s.timing_source == "missing" for s in segs)


# ------------------------------------------------------------------ splitting
def test_chunk_text_respects_limit_and_preserves_words():
    text = "Your father borrowed four million dollars from my family eleven years ago, and he signed a contract promising that if he ever failed to pay, his only daughter would marry the eldest Cole son."
    chunks = chunk_text(text, 84)
    assert all(len(c) <= 84 for c in chunks)
    assert " ".join(chunks).split() == text.split()


def test_split_divides_original_window_proportionally():
    dialogue, _, _ = extract_dialogue(["[00:00:10,000 --> 00:00:20,000] A: " + "word " * 40])
    segs = split_subtitles(dialogue, Thresholds(max_chars_per_segment=60))
    assert len(segs) >= 3
    assert segs[0].start_ms == 10000 and segs[-1].end_ms == 20000
    for a, b in zip(segs, segs[1:]):
        assert a.end_ms == b.start_ms  # contiguous, inside the original cue
    assert all(s.timing_source == "derived_split" for s in segs)


def test_short_line_keeps_original_timing():
    dialogue, _, _ = extract_dialogue(["[00:00:01,000 --> 00:00:02,600] MAYA: Who are you?"])
    s = split_subtitles(dialogue)[0]
    assert (s.start_ms, s.end_ms, s.timing_source, s.text) == (1000, 2600, "original", "Who are you?")


def test_wrap_text_balances_two_lines():
    lines = wrap_text("Your father borrowed four million dollars from my family", 42)
    assert len(lines) == 2 and all(len(l) <= 42 for l in lines)
    assert abs(len(lines[0]) - len(lines[1])) <= 10


# ------------------------------------------------------------------ readability
def test_reading_speed_calculation():
    s = seg("a", "x" * 34, 0, 2000)  # 34 chars / 2.0 s = 17.0 cps
    r = check_readability([s], Thresholds(max_cps=17)).segments["a"]
    assert r.metrics.cps == 17.0 and r.metrics.duration_s == 2.0
    assert not any(i.code == "reading_speed" for i in r.issues)
    s2 = seg("b", "x" * 40, 0, 2000)  # 20 cps
    r2 = check_readability([s2], Thresholds(max_cps=17)).segments["b"]
    assert r2.metrics.cps == 20.0
    assert any(i.code == "reading_speed" and i.severity == "warning" for i in r2.issues)
    s3 = seg("c", "x" * 60, 0, 2000)  # 30 cps > 1.25x -> error
    assert any(i.code == "reading_speed" and i.severity == "error" for i in check_readability([s3]).segments["c"].issues)


def test_overlap_detection():
    a = seg("a", "First.", 1000, 3000, 0)
    b = seg("b", "Second.", 2500, 4000, 1)
    rep = check_readability([a, b])
    ov = [i for i in rep.segments["b"].issues if i.code == "overlap"]
    assert ov and ov[0].value == 0.5
    assert not any(i.code == "overlap" for i in rep.segments["a"].issues)


def test_duration_empty_missing_invalid_and_long_checks():
    th = Thresholds()
    segs = [
        seg("short", "Hi.", 0, 500, 0),
        seg("long", "Okay.", 1000, 9000, 1),
        seg("empty", "", 10000, 11000, 2),
        seg("missing", "No timing.", None, None, 3),
        seg("invalid", "Backwards.", 13000, 12000, 4),
        seg("big", "This subtitle is extremely long and keeps going well beyond the eighty-four character limit for one card.", 20000, 30000, 5),
    ]
    rep = check_readability(segs, th)
    codes = {k: {i.code for i in v.issues} for k, v in rep.segments.items()}
    assert "too_short" in codes["short"]
    assert "too_long_duration" in codes["long"]
    assert "empty_text" in codes["empty"]
    assert "missing_timing" in codes["missing"]
    assert "invalid_timing" in codes["invalid"]
    assert {"too_many_chars", "too_many_lines"} <= codes["big"]
    assert rep.segments["short"].score < 100 and rep.average_score is not None
    assert "not universal standards" in rep.disclaimer


def test_thresholds_are_configurable():
    s = seg("a", "x" * 40, 0, 2000)  # 20 cps
    assert any(i.code == "reading_speed" for i in check_readability([s], Thresholds(max_cps=17)).segments["a"].issues)
    assert not any(i.code == "reading_speed" for i in check_readability([s], Thresholds(max_cps=21)).segments["a"].issues)
    with pytest.raises(ValueError):
        Thresholds(min_duration_s=5, max_duration_s=2)


def test_difficult_language_flagged_as_info():
    s = seg("a", "An unprecedented, catastrophically ill-advised acquisition.", 0, 5000)
    issues = check_readability([s]).segments["a"].issues
    d = [i for i in issues if i.code == "difficult_words"]
    assert d and d[0].severity == "info"


# ------------------------------------------------------------------ exports
def test_generate_srt_format_and_skips_untimed():
    segs = [seg("a", "Who are you?", 1000, 2600, 0), seg("b", "No timing.", None, None, 1),
            seg("c", "Backwards.", 5000, 4000, 2), seg("d", "The man who owns your debt, and your father's too.", 2800, 5200, 3)]
    srt, skipped = generate_srt(segs)
    assert skipped == ["b", "c"]
    blocks = srt.strip().split("\n\n")
    assert len(blocks) == 2
    assert blocks[0] == "1\n00:00:01,000 --> 00:00:02,600\nWho are you?"
    assert blocks[1].startswith("2\n00:00:02,800 --> 00:00:05,200\n")
    assert all(len(l) <= 42 for l in blocks[1].split("\n")[2:])


def test_generate_csv_has_row_per_segment(sample_texts):
    ep = parse_screenplay(sample_texts[0][1], sample_texts[0][0])[0]
    segs = split_subtitles(ep.dialogue)
    csv_text = generate_csv(segs, check_readability(segs))
    rows = csv_text.strip().splitlines()
    assert rows[0].startswith("index,character,start,end")
    assert len(rows) == len(segs) + 1


# ------------------------------------------------------------------ structured production-script format
STRUCTURED = """EPISODE NUMBER: Episode 7
EPISODE LOGLINE: A test logline that must never become dialogue.
CONTINUITY NOTES: Notes that must never become dialogue either.

--- SCRIPT START ---

SCENE 01
Scene heading: INT. TEST HALL – NIGHT
Scene start: 00:00.00
Scene end: 00:20.00

Actions and dialogue:

**CAMERA:**
Start: (00:00.00) | End: (00:03.00)
Wide shot of an empty hall.

**ANNA (Quiet, Nervous):**
Start: (00:01.20) | End: (00:03.40)
"Is anyone here?"

**ACTION:**
Start: (00:03.00) | End: (00:05.00)
A door creaks open.

**GUARD (O.S.) (Firm):**
Start: (00:03.20) | End: (00:05.10)
"Nobody enters after midnight."

**SOUND FX:**
Start: (00:05.00) | End: (00:06.00)
Thunder.

--- SCRIPT END ---
"""


def test_structured_script_format():
    eps = parse_screenplay(STRUCTURED, "episode-007.txt")
    assert len(eps) == 1 and eps[0].title == "Episode 7"
    d = eps[0].dialogue
    assert [(x.character, x.text) for x in d] == [("ANNA", "Is anyone here?"), ("GUARD", "Nobody enters after midnight.")]
    assert (d[0].start_ms, d[0].end_ms, d[0].parenthetical) == (1200, 3400, "Quiet, Nervous")
    assert d[1].parenthetical == "O.S.; Firm"
    assert d[0].scene == "INT. TEST HALL – NIGHT"
    assert eps[0].warnings == []
    segs = split_subtitles(d)
    rep = check_readability(segs)
    assert any(i.code == "overlap" for i in rep.segments[segs[1].id].issues)  # 3.2s starts before 3.4s
