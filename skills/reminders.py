import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TIMEZONE = ZoneInfo("Europe/Warsaw")
DB_PATH = Path.home() / "jarvis" / "data" / "jarvis.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            due_at TEXT NOT NULL,
            text TEXT NOT NULL,
            fired INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def add_reminder(due_at: datetime, text: str):
    due_at = due_at.astimezone(TIMEZONE)
    text = text.strip()

    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO reminders(due_at, text, fired, created_at)
            VALUES(?, ?, 0, ?)
            """,
            (
                due_at.isoformat(timespec="seconds"),
                text,
                datetime.now(TIMEZONE).isoformat(timespec="seconds"),
            ),
        )
        conn.commit()
        return cursor.lastrowid


def pending_reminders(limit=20):
    now = datetime.now(TIMEZONE).isoformat(timespec="seconds")

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, due_at, text
            FROM reminders
            WHERE fired = 0 AND due_at > ?
            ORDER BY due_at ASC
            LIMIT ?
            """,
            (now, int(limit)),
        ).fetchall()

    return [
        {
            "id": row[0],
            "due_at": datetime.fromisoformat(row[1]),
            "text": row[2],
        }
        for row in rows
    ]


def has_due_reminders():
    now = datetime.now(TIMEZONE).isoformat(timespec="seconds")

    with _connect() as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM reminders
            WHERE fired = 0 AND due_at <= ?
            LIMIT 1
            """,
            (now,),
        ).fetchone()

    return row is not None


def pop_due_reminders(limit=10):
    now = datetime.now(TIMEZONE).isoformat(timespec="seconds")

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, due_at, text
            FROM reminders
            WHERE fired = 0 AND due_at <= ?
            ORDER BY due_at ASC
            LIMIT ?
            """,
            (now, int(limit)),
        ).fetchall()

        ids = [row[0] for row in rows]

        if ids:
            placeholders = ",".join("?" for _ in ids)
            conn.execute(
                f"""
                UPDATE reminders
                SET fired = 1
                WHERE id IN ({placeholders})
                """,
                ids,
            )
            conn.commit()

    return [
        {
            "id": row[0],
            "due_at": datetime.fromisoformat(row[1]),
            "text": row[2],
        }
        for row in rows
    ]


def cancel_latest():
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, text
            FROM reminders
            WHERE fired = 0
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

        if not row:
            return None

        conn.execute(
            "DELETE FROM reminders WHERE id = ?",
            (row[0],),
        )
        conn.commit()

    return row[1]


def parse_reminder_command(text: str):
    """
    Obsługiwane przykłady:
      przypomnij mi za 10 minut żeby zadzwonić
      przypomnij mi za 2 godziny o nauce
      przypomnij mi o 18:30 żeby sprawdzić maila
      przypomnij mi jutro o 08:00 o zajęciach
    """
    raw = text.strip()
    lower = raw.lower()
    now = datetime.now(TIMEZONE)

    relative = re.search(
        r"przypomnij mi za\s+(\d+)\s*"
        r"(minut(?:ę|y)?|min|godzin(?:ę|y)?|h)"
        r"\s*(?:żeby|zeby|o)?\s*(.*)",
        lower,
    )

    if relative:
        value = int(relative.group(1))
        unit = relative.group(2)
        message = relative.group(3).strip(" .")

        if not message:
            message = "o tym, o co prosiłeś"

        if unit.startswith("min"):
            due = now + timedelta(minutes=value)
        else:
            due = now + timedelta(hours=value)

        return due, message

    tomorrow = "jutro" in lower

    absolute = re.search(
        r"przypomnij mi(?: jutro)? o\s+"
        r"([01]?\d|2[0-3])(?::|\s)([0-5]\d)"
        r"\s*(?:żeby|zeby|o)?\s*(.*)",
        lower,
    )

    if absolute:
        hour = int(absolute.group(1))
        minute = int(absolute.group(2))
        message = absolute.group(3).strip(" .")

        if not message:
            message = "o tym, o co prosiłeś"

        target_date = now.date()

        if tomorrow:
            target_date += timedelta(days=1)

        due = datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            hour,
            minute,
            tzinfo=TIMEZONE,
        )

        if not tomorrow and due <= now:
            due += timedelta(days=1)

        return due, message

    return None


def format_pending(limit=5):
    rows = pending_reminders(limit)

    if not rows:
        return "Nie masz ustawionych przypomnień."

    parts = []

    for row in rows:
        parts.append(
            f"{row['due_at'].strftime('%d.%m o %H:%M')}: "
            f"{row['text']}"
        )

    return "Najbliższe przypomnienia: " + "; ".join(parts) + "."
