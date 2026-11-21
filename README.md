# FrameFlow AI — Microdrama Subtitle & Dialogue Optimizer

FrameFlow AI helps screenplay editors turn TXT screenplays into readable subtitles for short-form vertical dramas.
It pulls out the timestamped dialogue, splits it into subtitle cards, checks readability with deterministic rules,
suggests shorter lines through OpenRouter, and exports SRT, CSV and JSON files.

**Stack:** React 18 + TypeScript + Tailwind CSS v4 + Lucide icons (Vite) · Python FastAPI + Pydantic v2 · SQLite · OpenRouter.
Runs fine on an 8 GB laptop and needs no GPU.

---

## 1. Run it locally

You need **Python 3.10+** and **Node.js 18+**.

### Backend (terminal 1)

```bash
cd frameflow-ai/backend
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows (PowerShell):
# .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp ../.env.example .env          # Windows: copy ..\.env.example .env
# edit .env and set OPENROUTER_API_KEY=sk-or-v1-...
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

### Frontend (terminal 2)

```bash
cd frameflow-ai/frontend
npm install
npm run dev
```

Open **http://localhost:5173**. Vite forwards `/api` requests to the backend on port 8000.

### Run the tests

```bash
cd frameflow-ai/backend
pytest -v
```

### Try it in 30 seconds

Click **Load synthetic demo** on the Dashboard. This creates a project from `sample_data/synthetic/`,
which holds two fictional episodes. They are labelled **SYNTHETIC** everywhere in the UI and in exported filenames.

> **No API key?** Everything still works except the two AI buttons (AI segmentation, Optimise). Those return a clear
> error, record the failed call, and leave your subtitles unchanged.

---

## 2. Pages

| Page | What it does |
|---|---|
| **Dashboard** | Live totals: episodes processed, segments, readability issues, average quality score, 14-day activity (episodes, AI calls ok/failed, edits), issue breakdown, score distribution, recent projects (open/delete). |
| **Upload Studio** | Drag-and-drop multiple `.txt` files, detected episode names, a syntax-highlighted screenplay preview (timestamps, characters, missing timing), and a **Start analysis** button. |
| **Subtitle Editor** | One card per subtitle with character, parenthetical, editable text, editable start/end time, live chars/CPS/duration, timing source, issues and filters. Also **Re-split** and **AI segmentation**. |
| **Readability Intelligence** | Card-by-card metrics against configurable thresholds, severity/type filters, issue chart, and an inline threshold editor. |
| **AI Dialogue Optimizer** | Shows original and suggested text side by side, before/after CPS, rationale and plot-detail guard warnings. Lets you edit, **Accept**, **Reject** or **Restore original**. Includes a model switcher and the raw AI outputs viewer. |
| **Timeline Preview** | A horizontal, zoomable timeline whose cards show timestamp, character, text and status, with bars for real duration. Overlaps are shown in red, untimed cards sit in a tray, and a phone-frame preview shows the selected subtitle. |
| **Export Centre** | Download SRT, CSV report or JSON analysis per episode, or a ZIP of the whole project, with a live SRT preview. |
| **Settings** | API key status, default model (with a model list from OpenRouter), and all editorial thresholds. |

---

## 3. Screenplay format

Formats can be mixed within one file:

```text
TITLE: My Series
EPISODE: 1 — Pilot

INT. OFFICE - NIGHT
[00:00:01,000 --> 00:00:03,500] MAYA: Who are you?
[00:00:04.0 - 00:00:09.5] ADRIAN (quietly): Someone who knows.
00:00:10,000 --> 00:00:12,000 MAYA: Brackets are optional.

[00:00:12,000 --> 00:00:18,500]
ADRIAN
(turning)
Block-style dialogue, possibly over
several lines.

[??:??:?? --> ??:??:??] LILY: Placeholder = missing timing.
LILY: No timestamp at all = missing timing.
[00:00:28,500 -->] ADRIAN: Start only = missing end.
```

- Several `EPISODE` headings in one file produce several episodes.
- Scene headings, action lines, transitions (`CUT TO:`) and `#` comments are not treated as dialogue.
- A file containing the word **SYNTHETIC** in its header is flagged as synthetic data.

---

## 4. How processing works (`backend/app/`)

| Function | File | Type |
|---|---|---|
| `parse_screenplay()` | `processing.py` | deterministic: splits episodes, parses timestamps |
| `extract_dialogue()` | `processing.py` | deterministic: characters, parentheticals, verbatim text, timing status |
| `split_subtitles()` | `processing.py` | deterministic: sentence → clause → word boundaries, ≤ max chars per card |
| `check_readability()` | `processing.py` | deterministic: all checks below |
| `generate_srt()` | `processing.py` | deterministic: wrapped lines, sorted by start time |
| `optimize_dialogue()` | `ai.py` | OpenRouter + Pydantic validation + plot-detail guard |
| `ai_segment_dialogue()` | `ai.py` | OpenRouter + word-for-word verification |

### Timing rules: timestamps are never invented
- Timestamps come only from the screenplay or from manual edits.
- When a long line is split into several cards, the **original cue window** is divided by character count.
  Those cards are labelled *"Split of original cue"* (`derived_split`), so the timing stays inside what the script specified.
- Lines without timing are labelled **Missing — enter manually**. They appear in an "untimed" tray on the timeline
  and are **left out of the SRT** (the export reports how many were skipped). CSV and JSON include them.

### Readability checks (Python only)
Very long lines, too many lines, too many characters per card, reading speed (characters incl. spaces ÷ seconds),
too short or too long on screen, overlaps with the previous card, empty segments, missing or invalid timing, and
potentially difficult language (long or many-syllable words, long sentences; a heuristic, shown as *info*).

**These are editorial guidelines, not universal standards.** Defaults: 42 chars/line, 2 lines, 84 chars/card,
17 CPS, 1–7 s. Change them in Settings to match your house style or distributor spec.
The quality score is a simple heuristic: 100 − 25 per error − 10 per warning − 4 per info, never below 0.

### AI safeguards
- The API key lives only on the backend (`OPENROUTER_API_KEY`) and never reaches the browser.
- Default model is `openrouter/free`. You can switch per request (Optimizer) or globally (Settings).
- Every reply must parse as JSON and pass a Pydantic schema. Anything else is rejected with `invalid_output`.
- **Optimiser guard:** numbers, mid-sentence names/places and negations from the original are checked against
  the suggestion. Anything missing is shown as a warning, and suggestions are never applied automatically.
- **Segmentation guard:** an AI split is accepted only if it uses the exact original words in order and every card
  fits the limit. Otherwise the deterministic split is kept.
- On any failure (no key, network, timeout, HTTP 401/402/404/429, bad JSON) the API returns 503/502 with an
  explanation, the failed call is logged, and the deterministic results are untouched. No AI response is hardcoded.

### Raw AI outputs
Every call, successful or failed, is saved verbatim to `raw_ai_outputs/`, to the `ai_runs` table, to the
Optimizer's *Raw AI outputs* panel, and to each JSON export. See `raw_ai_outputs/README.md`.
To capture real model outputs, run `python scripts/capture_raw_ai_outputs.py` from `backend/`.

---

## 5. Tests and results

`backend/tests/` — 61 tests:

| Requirement | Tests |
|---|---|
| TXT upload | `test_txt_upload_decoding`, `test_upload_without_dialogue_is_rejected`, `test_multiple_files_create_multiple_episodes`, `test_upload_txt_and_episode_flow`*, `test_reject_non_txt`* |
| Dialogue extraction | `test_sample_episode_1_extraction`, `test_multiple_episodes_in_one_file`, `test_scene_headings_and_actions_not_dialogue` |
| Subtitle generation | `test_chunk_text_respects_limit_and_preserves_words`, `test_split_divides_original_window_proportionally`, `test_short_line_keeps_original_timing`, `test_no_timestamps_are_invented` |
| Character identification | `test_character_identification` |
| Reading speed | `test_reading_speed_calculation`, `test_thresholds_are_configurable` |
| Timestamp validation | `test_parse_timestamp`, `test_bad_timestamps_raise`, `test_overlap_detection`, `test_missing_invalid_and_partial_timing_flagged`, `test_duration_empty_missing_invalid_and_long_checks`, `test_manual_timing_fixes_missing_issue` |
| Dialogue rewriting | `test_optimize_valid_reply_is_validated_and_guarded`, `test_optimize_accept_reject_flow`, `test_guard_detects_dropped_negation_and_names`, `test_ai_segment_*` |
| SRT download | `test_generate_srt_format_and_skips_untimed`, `test_exports`, `test_upload_txt_and_episode_flow`* |
| API failure handling | `test_missing_api_key_raises_unavailable`, `test_network_failure_raises_unavailable`, `test_timeout_raises_unavailable`, `test_http_errors_are_reported_with_hints`, `test_optimize_invalid_json_raises_invalid_output`, `test_ai_failure_keeps_deterministic_results_and_logs_run`, `test_optimize_without_key_returns_503_and_checks_still_work`* |

\* in `tests/test_api.py` (FastAPI `TestClient`).

**Actual results:** `test_results/pytest_output.txt` — **60 passed, 1 skipped**. The skipped file is `test_api.py`,
because FastAPI and httpx could not be installed in the sandbox where this was built. It runs automatically after
`pip install -r requirements.txt`. AI tests use a scripted fake HTTP session, so they run offline and give
deterministic results; that fake exists only in `tests/`.

**Frontend verification done during the build:** the full TypeScript source bundled cleanly with esbuild, and the
Tailwind v4 CSS compiled. I then clicked through every page in headless Chromium against the real service layer:
loaded the demo, fixed a missing timestamp, saw the AI optimiser fail cleanly without a key, downloaded an SRT,
previewed an upload, opened Settings, and accepted a suggestion. The only console error was the expected 503.
`test_results/sample_export_SYNTHETIC_Episode_1.srt` is a real SRT downloaded during that run.
`npm install` / `vite build` could not run there because there was no npm registry access, so please run
`npm run build` once locally.

---

## 6. Project layout

```text
frameflow-ai/
├── .env.example
├── README.md
├── backend/
│   ├── requirements.txt
│   ├── app/            main.py (FastAPI routes) · service.py · processing.py · ai.py · db.py · models.py · config.py
│   ├── scripts/        capture_raw_ai_outputs.py
│   └── tests/          conftest.py · test_processing.py · test_ai.py · test_service.py · test_api.py
├── frontend/
│   ├── package.json · vite.config.ts · tsconfig.json · index.html
│   └── src/            App.tsx · api.ts · types.ts · utils.ts · context.ts · components/ · pages/
├── sample_data/synthetic/   EP01_the_contract.txt · EP02_the_wedding.txt   (SYNTHETIC — fictional)
├── raw_ai_outputs/          verbatim AI call records
└── test_results/            pytest_output.txt · sample SRT export
```

The SQLite database is created at `backend/frameflow.db` on first run. Delete it to start fresh.

## 7. Synthetic data notice

Everything in `sample_data/synthetic/` is **fictional data written for this demo**. It deliberately includes short
and long dialogue, five characters, block and inline formats, two overlapping cues, missing timestamps (none,
placeholder, start-only), an end-before-start cue, an empty line and a line with an extremely high reading speed.
Projects built from it are marked **SYNTHETIC** in the UI, the dashboard, export filenames and the
`data_origin` field of JSON reports.
