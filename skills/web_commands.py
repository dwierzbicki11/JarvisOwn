import sqlite3
from contextlib import closing
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

    conn.execute("""
        CREATE TABLE IF NOT EXISTS web_command_results (
            command_id INTEGER PRIMARY KEY,
            answer TEXT NOT NULL,
            finished_at TEXT NOT NULL
        )
    """)

    conn.commit()
    return conn


def submit_command(text):
    text = text.strip()

    if not text:
        return None

    with closing(_connect()) as conn:
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
    with closing(_connect()) as conn:
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
    with closing(_connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
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


def complete_command(command_id, answer):
    with closing(_connect()) as conn, conn:
        conn.execute("""INSERT OR IGNORE INTO web_command_results(command_id, answer, finished_at)
            SELECT id, ?, ? FROM web_commands WHERE id=? AND handled=1""",
                     (answer, datetime.now().isoformat(timespec="seconds"), command_id))


def command_result(command_id):
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("""SELECT c.id, c.handled, r.answer, r.finished_at
            FROM web_commands c LEFT JOIN web_command_results r ON r.command_id=c.id
            WHERE c.id=?""", (command_id,)).fetchone()
    if row is None:
        return None
    return {"id": row["id"], "answer": row["answer"], "finished_at": row["finished_at"],
            "state": "done" if row["finished_at"] else "processing" if row["handled"] else "queued"}


def recover_interrupted_commands():
    """Run once before the core worker starts. Never replay a possibly executed action."""
    with closing(_connect()) as conn, conn:
        conn.execute("""INSERT OR IGNORE INTO web_command_results(command_id, answer, finished_at)
            SELECT id, ?, ? FROM web_commands WHERE handled=1""",
                     ("JARVIS uruchomił się ponownie bez potwierdzenia wyniku tego polecenia. "
                      "Sprawdź aktualny stan przed ponowieniem.",
                      datetime.now().isoformat(timespec="seconds")))
