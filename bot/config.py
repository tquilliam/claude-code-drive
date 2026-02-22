"""Configuration module - loads and validates environment variables."""

import os
import sys


def _require(name: str) -> str:
    """Get required environment variable or exit."""
    val = os.getenv(name)
    if not val:
        print(f"[FATAL] Missing required env var: {name}", file=sys.stderr)
        sys.exit(1)
    return val


# Required vars
TELEGRAM_BOT_TOKEN = _require("TELEGRAM_BOT_TOKEN")
ANTHROPIC_API_KEY = _require("ANTHROPIC_API_KEY")
ALLOWED_TELEGRAM_IDS_RAW = _require("ALLOWED_TELEGRAM_IDS")

# Optional vars with defaults
PROJECT_ROOT = os.getenv("PROJECT_ROOT", "/Users/thom/Claude Code Drive")
DB_PATH = os.getenv("DB_PATH", os.path.join(PROJECT_ROOT, "bot", "bot.db"))
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-6")
AGENT_MAX_TURNS = int(os.getenv("AGENT_MAX_TURNS", "40"))
PROGRESS_INTERVAL_SECONDS = int(os.getenv("PROGRESS_INTERVAL_SECONDS", "30"))
BASH_TIMEOUT_SECONDS = int(os.getenv("BASH_TIMEOUT_SECONDS", "120"))

# Telegram-specific optimization settings
TELEGRAM_OPTIMIZE = os.getenv("TELEGRAM_OPTIMIZE", "true").lower() == "true"
TELEGRAM_MAX_TOKENS = int(os.getenv("TELEGRAM_MAX_TOKENS", "4096"))  # Reduced from 8096
TELEGRAM_REQUEST_DELAY = float(os.getenv("TELEGRAM_REQUEST_DELAY", "0.5"))  # Seconds between requests

# Parse allowed user IDs
def parse_allowed_ids(raw: str) -> set[int]:
    """Parse comma-separated Telegram user IDs."""
    ids = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return ids


ALLOWED_TELEGRAM_IDS = parse_allowed_ids(ALLOWED_TELEGRAM_IDS_RAW)

if not ALLOWED_TELEGRAM_IDS:
    print("[FATAL] ALLOWED_TELEGRAM_IDS must contain at least one valid integer", file=sys.stderr)
    sys.exit(1)

# Ensure PROJECT_ROOT exists
if not os.path.isdir(PROJECT_ROOT):
    print(f"[FATAL] PROJECT_ROOT does not exist: {PROJECT_ROOT}", file=sys.stderr)
    sys.exit(1)
