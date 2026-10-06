import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path.home() / "jarvis" / "data" / "jarvis.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _connect():
    conn = sqlite3.connect(
        DB_PATH,
        timeout=5,
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS web_commands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            handled INTEGER NOT NULL DEFAULT 0
        )
        """
    )

    conn.commit()
    return conn


def submit_command(text):
    text = text.strip()

    if not text:
        return None

    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO web_commands(text, created_at, handled)
            VALUES(?, ?, 0)
            """,
            (
                text,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        conn.commit()
        return cursor.lastrowid


def has_pending_commands():
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM web_commands
            WHERE handled = 0
            LIMIT 1
            """
        ).fetchone()

    return row is not None


def pop_pending_commands(limit=5):
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, text, created_at
            FROM web_commands
            WHERE handled = 0
            ORDER BY id ASC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()

        ids = [row[0] for row in rows]

        if ids:
            placeholders = ",".join("?" for _ in ids)
            conn.execute(
                f"""
                UPDATE web_commands
                SET handled = 1
                WHERE id IN ({placeholders})
                """,
                ids,
            )
            conn.commit()

    return [
        {
            "id": row[0],
            "text": row[1],
            "created_at": row[2],
        }
        for row in rows
    ]
