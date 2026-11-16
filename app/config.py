"""Central configuration. Every value can be overridden with an environment variable."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("SMARTINTAKE_DATA_DIR", BASE_DIR / "data"))


def db_path() -> Path:
    return Path(os.environ.get("SMARTINTAKE_DB", DATA_DIR / "smartintake.db"))


def model_path() -> Path:
    return Path(os.environ.get("SMARTINTAKE_MODEL", DATA_DIR / "model.pkl"))


# Routing rules (defaults; the supervisor can change them at run time, see `setting` table)
DEFAULT_CONFIDENCE_THRESHOLD = 0.80
DEFAULT_DUPLICATE_RADIUS_M = 50.0
DEFAULT_DUPLICATE_WINDOW_DAYS = 14

# Requests containing any of these phrases never go to the model: a human sees them first.
SAFETY_KEYWORDS = (
    "gas leak",
    "smell of gas",
    "smell gas",
    "downed wire",
    "downed power line",
    "power line down",
    "live wire",
    "exposed wire",
    "sparking",
    "flooding",
    "flooded",
    "sinkhole",
    "fire",
    "collapsed",
    "collapse",
    "explosion",
    "carbon monoxide",
)

# Hosted LLM backend (optional). Without an API key the local model is used.
LLM_API_KEY_ENV = "ANTHROPIC_API_KEY"
LLM_MODEL = os.environ.get("SMARTINTAKE_LLM_MODEL", "claude-haiku-5-5")
