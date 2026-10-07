"""Small local study activity tracker for the educational assistant."""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path.home() / "jarvis" / "data" / "study_progress.db"


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS study_activity (
            subject TEXT PRIMARY KEY,
            interactions INTEGER NOT NULL DEFAULT 0,
            last_at TEXT NOT NULL
        )
        """
    )
    return conn


def record_interaction(subject: str, kind: str = "question"):
    subject = (subject or "").strip().lower()
    if not subject:
        return False
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO study_activity(subject, interactions, last_at)
            VALUES (?, 1, ?)
            ON CONFLICT(subject) DO UPDATE SET
                interactions = study_activity.interactions + 1,
                last_at = excluded.last_at
            """,
            (subject, now),
        )
    return True


def summary():
    with _connect() as conn:
        rows = conn.execute(
            "SELECT subject, interactions, last_at FROM study_activity ORDER BY interactions DESC, subject"
        ).fetchall()
    return [
        {"subject": row[0], "interactions": row[1], "last_at": row[2]}
        for row in rows
    ]


def format_summary():
    rows = summary()
    if not rows:
        return "Nie mam jeszcze zapisanej aktywności nauki."
    def noun(count):
        if count == 1:
            return "interakcja"
        if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
            return "interakcje"
        return "interakcji"

    details = "; ".join(
        f"{row['subject']}: {row['interactions']} {noun(row['interactions'])}"
        for row in rows
    )
    return "Postęp nauki: " + details + "."

