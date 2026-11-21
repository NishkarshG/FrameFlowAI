"""Run the real OpenRouter pipeline on the SYNTHETIC sample and save raw, unedited outputs.

Usage (from backend/):
    python scripts/capture_raw_ai_outputs.py [--model openrouter/free]

Every call (success or failure) is written verbatim to ../raw_ai_outputs/ as JSON,
including the exact request messages and the model's raw text reply.
Uses a temporary in-memory database, so your projects are not touched.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config, service  # noqa: E402
from app.db import Database  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=config.DEFAULT_MODEL)
    args = ap.parse_args()

    if not config.get_api_key():
        print("OPENROUTER_API_KEY is not set (backend/.env). The failure will still be recorded as a raw output.")

    db = Database(":memory:")
    project = service.create_sample_project(db)
    print(f"Raw outputs folder: {config.RAW_AI_DIR}")
    for ep in project["episodes"]:
        for kind, fn in (("segment", service.run_ai_segment), ("optimize", service.run_optimize)):
            try:
                if kind == "optimize":
                    res = fn(db, ep["id"], None, args.model)
                else:
                    res = fn(db, ep["id"], args.model)
                print(f"[OK]   {ep['name']} / {kind}: {res['ai_result']}")
            except service.ServiceError as e:
                print(f"[FAIL] {ep['name']} / {kind}: HTTP {e.status} — {e.message}")
    runs = db.list_ai_runs()
    print(f"{len(runs)} AI runs recorded ({sum(r['status'] == 'success' for r in runs)} successful).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
