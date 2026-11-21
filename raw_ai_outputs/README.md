# Raw, unedited AI outputs

Every OpenRouter call FrameFlow AI makes is written here verbatim as one JSON file:
`<timestamp>_<kind>_<status>_<id>.json`. Each file contains the model id, the exact request messages,
the model's raw text reply (unedited), the Pydantic-validated result, and any error.

The same records are stored in SQLite (`ai_runs` table), shown under **AI Dialogue Optimizer → Raw AI outputs**,
and included in every JSON analysis export (`ai_runs_raw`).

## What is in this folder right now

The four `*_failed_*.json` files were produced by actually running
`python scripts/capture_raw_ai_outputs.py` in the build environment, which had **no OpenRouter API key and no
network access to openrouter.ai**. They are genuine records of the "API unavailable" path: the request was
refused before any model was called, so there is no model text in them.

**No successful model outputs are included, because none were generated.** Nothing here was written by hand
or edited.

## Capture real model outputs

```bash
cd backend
# with OPENROUTER_API_KEY set in backend/.env
python scripts/capture_raw_ai_outputs.py --model openrouter/free
```

This runs AI segmentation and dialogue optimisation on both synthetic sample episodes (using a throwaway
in-memory database) and saves every raw reply to this folder.
