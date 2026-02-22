"""Access control - enforce allowlist of Telegram user IDs."""

from config import ALLOWED_TELEGRAM_IDS


def is_allowed(telegram_id: int) -> bool:
    """Check if a Telegram user ID is in the allowlist."""
    return telegram_id in ALLOWED_TELEGRAM_IDS
