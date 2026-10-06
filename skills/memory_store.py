import sqlite3
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
