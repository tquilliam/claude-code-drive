"""Database module - SQLite schema and conversation history CRUD."""

import sqlite3
import json
import uuid
from datetime import datetime
from config import DB_PATH


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    telegram_id    INTEGER PRIMARY KEY,
    username       TEXT,
    first_seen     TEXT NOT NULL,
    last_active    TEXT NOT NULL,
    is_allowed     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS conversations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id    INTEGER NOT NULL,
    session_id     TEXT NOT NULL UNIQUE,
    created_at     TEXT NOT NULL,
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
);

CREATE TABLE IF NOT EXISTS messages (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    role           TEXT NOT NULL,
    content        TEXT NOT NULL,
    timestamp      TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);

CREATE TABLE IF NOT EXISTS tasks (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id    INTEGER NOT NULL,
    chat_id        INTEGER NOT NULL,
    command        TEXT NOT NULL,
    arguments      TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'pending',
    started_at     TEXT,
    completed_at   TEXT,
    result_path    TEXT,
    error_message  TEXT,
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_tasks_telegram_id ON tasks(telegram_id);
CREATE INDEX IF NOT EXISTS idx_conversations_telegram_id ON conversations(telegram_id);
"""


def get_connection() -> sqlite3.Connection:
    """Get a database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database schema."""
    with get_connection() as conn:
        conn.executescript(SCHEMA)


def get_recent_messages(telegram_id: int, limit: int = 20) -> list[dict]:
    """
    Retrieve recent messages for a user for conversation context.
    Returns Anthropic-format messages list (role + content).
    """
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT m.role, m.content
            FROM messages m
            JOIN conversations c ON m.conversation_id = c.id
            WHERE c.telegram_id = ?
            ORDER BY m.id DESC
            LIMIT ?
        """, (telegram_id, limit)).fetchall()

    messages = []
    for row in reversed(rows):  # oldest first
        try:
            content = json.loads(row["content"])
        except (json.JSONDecodeError, TypeError):
            content = row["content"]
        messages.append({
            "role": row["role"],
            "content": content,
        })
    return messages


def save_message(conversation_id: int, role: str, content):
    """Save a message to the database."""
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO messages (conversation_id, role, content, timestamp)
            VALUES (?, ?, ?, ?)
        """, (conversation_id, role, json.dumps(content), datetime.utcnow().isoformat()))


def create_or_get_session(telegram_id: int) -> int:
    """Get the most recent conversation ID for a user, or create a new one."""
    with get_connection() as conn:
        row = conn.execute("""
            SELECT id FROM conversations WHERE telegram_id = ?
            ORDER BY id DESC LIMIT 1
        """, (telegram_id,)).fetchone()
        if row:
            return row["id"]
        cursor = conn.execute("""
            INSERT INTO conversations (telegram_id, session_id, created_at)
            VALUES (?, ?, ?)
        """, (telegram_id, str(uuid.uuid4()), datetime.utcnow().isoformat()))
        return cursor.lastrowid


def register_user(telegram_id: int, username: str | None):
    """Register or update a user."""
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE users SET username = ?, last_active = ? WHERE telegram_id = ?",
                (username, datetime.utcnow().isoformat(), telegram_id)
            )
        else:
            conn.execute("""
                INSERT INTO users (telegram_id, username, first_seen, last_active, is_allowed)
                VALUES (?, ?, ?, ?, ?)
            """, (telegram_id, username, datetime.utcnow().isoformat(), datetime.utcnow().isoformat(), 1))
