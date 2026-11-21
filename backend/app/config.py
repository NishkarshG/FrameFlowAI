"""Configuration loaded from environment variables (and an optional .env file)."""
from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent


def _load_dotenv() -> None:
    """Minimal .env loader (no extra dependency). Existing env vars win."""
    for candidate in (BACKEND_DIR / ".env", ROOT_DIR / ".env"):
        if not candidate.exists():
            continue
        for raw in candidate.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key.strip(), value)


_load_dotenv()

OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
DEFAULT_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")
AI_TIMEOUT_S = float(os.getenv("AI_TIMEOUT_SECONDS", "90"))
DB_PATH = os.getenv("FRAMEFLOW_DB", str(BACKEND_DIR / "frameflow.db"))
SAMPLE_DIR = Path(os.getenv("FRAMEFLOW_SAMPLE_DIR", str(ROOT_DIR / "sample_data" / "synthetic")))
RAW_AI_DIR = Path(os.getenv("FRAMEFLOW_RAW_AI_DIR", str(ROOT_DIR / "raw_ai_outputs")))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(2 * 1024 * 1024)))
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]


def get_api_key() -> str | None:
    """Read at call time so the key can be added without code changes."""
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    return key or None
