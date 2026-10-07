import sqlite3
import re
import unicodedata
from datetime import datetime
from pathlib import Path

DB_PATH = Path.home() / "jarvis" / "data" / "jarvis.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def remember(text: str):
    text = text.strip()

    if not text:
        return False

    with _connect() as conn:
        conn.execute(
            "INSERT INTO memories(text, created_at) VALUES(?, ?)",
            (text, datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()

    return True


def recent_memories(limit=12):
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, text, created_at
            FROM memories
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()

    return [
        {
            "id": row[0],
            "text": row[1],
            "created_at": row[2],
        }
        for row in rows
    ]


def memory_context(limit=8):
    rows = recent_memories(limit)

    if not rows:
        return ""

    rows.reverse()
    return "\n".join(f"- {row['text']}" for row in rows)


def search_memories(query: str, limit=8):
    """Find explicitly saved memories matching the user's topic.

    Search stays local and deliberately uses token matching instead of an
    external embedding service, which keeps the Raspberry Pi deployment
    private and predictable.
    """
    query = (query or "").strip()
    if not query:
        return []

    normalized = unicodedata.normalize("NFKD", query)
    normalized = "".join(
        char for char in normalized
        if not unicodedata.combining(char)
    ).lower()
    tokens = [
        token for token in re.findall(r"[a-z0-9ąćęłńóśźż]{3,}", normalized)
        if token not in {"co", "czym", "jest", "mam", "mnie", "moje", "moich"}
    ]
    if not tokens:
        return []

    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, text, created_at FROM memories ORDER BY id DESC"
        ).fetchall()

    scored = []
    for row in rows:
        text = row[1]
        folded = unicodedata.normalize("NFKD", text)
        folded = "".join(
            char for char in folded
            if not unicodedata.combining(char)
        ).lower()
        words = re.findall(r"[a-z0-9ąćęłńóśźż]{3,}", folded)
        score = 0
        for token in tokens:
            stem = token[:max(4, len(token) - 3)]
            if any(
                word == token
                or token in word
                or word in token
                or word.startswith(stem)
                for word in words
            ):
                score += 1
        if score:
            scored.append((score, row))

    scored.sort(key=lambda item: (-item[0], -item[1][0]))
    return [
        {"id": row[0], "text": row[1], "created_at": row[2]}
        for _, row in scored[:max(1, min(int(limit), 50))]
    ]


def forget_latest():
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, text
            FROM memories
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

        if not row:
            return None

        conn.execute(
            "DELETE FROM memories WHERE id = ?",
            (row[0],),
        )
        conn.commit()

    return row[1]


def clear_all():
    with _connect() as conn:
        conn.execute("DELETE FROM memories")
        conn.commit()

