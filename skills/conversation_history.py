import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path.home() / "jarvis"
DB_PATH = BASE_DIR / "data" / "conversation_history.db"
_LOCK = threading.Lock()


def _connect():
    DB_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    conn = sqlite3.connect(
        DB_PATH,
        timeout=5,
    )
    conn.row_factory = sqlite3.Row

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS conversation_turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            user_text TEXT NOT NULL,
            assistant_text TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_conversation_turns_created_at
        ON conversation_turns(created_at)
        """
    )

    return conn


def append_turn(
    user_text: str,
    assistant_text: str,
):
    user_text = (user_text or "").strip()
    assistant_text = (assistant_text or "").strip()

    if not user_text or not assistant_text:
        return False

    with _LOCK:
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO conversation_turns (
                    created_at,
                    user_text,
                    assistant_text
                )
                VALUES (?, ?, ?)
                """,
                (
                    datetime.now(
                        timezone.utc
                    ).isoformat(),
                    user_text,
                    assistant_text,
                ),
            )

    return True


def recent_turns(limit=10):
    limit = max(
        1,
        min(int(limit), 100),
    )

    with _LOCK:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    id,
                    created_at,
                    user_text,
                    assistant_text
                FROM conversation_turns
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    rows = list(reversed(rows))

    return [
        {
            "id": row["id"],
            "created_at": row["created_at"],
            "user": row["user_text"],
            "assistant": row["assistant_text"],
        }
        for row in rows
    ]


def last_turn():
    turns = recent_turns(
        limit=1
    )

    return turns[-1] if turns else None


def recent_messages(
    limit_messages=20,
):
    """
    Zwraca historię w formacie zgodnym z chat.completions.

    limit_messages dotyczy wiadomości, nie par rozmów.
    """
    limit_messages = max(
        2,
        min(int(limit_messages), 100),
    )

    turn_limit = max(
        1,
        (limit_messages + 1) // 2,
    )

    turns = recent_turns(
        limit=turn_limit
    )

    messages = []

    for turn in turns:
        messages.extend(
            [
                {
                    "role": "user",
                    "content": turn["user"],
                },
                {
                    "role": "assistant",
                    "content": turn["assistant"],
                },
            ]
        )

    return messages[-limit_messages:]


def format_recent_history(
    limit=6,
):
    turns = recent_turns(limit)

    if not turns:
        return "Historia rozmowy jest pusta."

    parts = []

    for turn in turns:
        parts.append(
            "Ty: "
            + turn["user"]
            + " | JARVIS: "
            + turn["assistant"]
        )

    return "Ostatnie rozmowy: " + " ; ".join(parts)


def clear_history():
    with _LOCK:
        with _connect() as conn:
            conn.execute(
                "DELETE FROM conversation_turns"
            )

    return True
