import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TIMEZONE = ZoneInfo("Europe/Warsaw")
DB_PATH = Path.home() / "jarvis" / "data" / "jarvis.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS focus_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT NOT NULL,
            started_at TEXT NOT NULL,
            ends_at TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            notified INTEGER NOT NULL DEFAULT 0,
            stopped_at TEXT
        )
        """
    )
    conn.commit()
    return conn


def start_focus(minutes, label="nauka"):
    minutes = max(1, min(int(minutes), 240))
    now = datetime.now(TIMEZONE)
    ends_at = now + timedelta(minutes=minutes)

    with _connect() as conn:
        conn.execute(
            """
            UPDATE focus_sessions
            SET active = 0, stopped_at = ?
            WHERE active = 1
            """,
            (now.isoformat(timespec="seconds"),),
        )
        cursor = conn.execute(
            """
            INSERT INTO focus_sessions(
                label, started_at, ends_at, active, notified
            )
            VALUES(?, ?, ?, 1, 0)
            """,
            (
                label.strip() or "nauka",
                now.isoformat(timespec="seconds"),
                ends_at.isoformat(timespec="seconds"),
            ),
        )
        conn.commit()

    return {
        "id": cursor.lastrowid,
        "label": label.strip() or "nauka",
        "started_at": now,
        "ends_at": ends_at,
        "minutes": minutes,
    }


def current_focus():
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, label, started_at, ends_at
            FROM focus_sessions
            WHERE active = 1
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

    if not row:
        return None

    now = datetime.now(TIMEZONE)
    ends_at = datetime.fromisoformat(row[3])
    remaining = max(
        0,
        round((ends_at - now).total_seconds() / 60),
    )

    return {
        "id": row[0],
        "label": row[1],
        "started_at": datetime.fromisoformat(row[2]),
        "ends_at": ends_at,
        "remaining_minutes": remaining,
        "expired": ends_at <= now,
    }


def stop_focus():
    now = datetime.now(TIMEZONE)

    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, label
            FROM focus_sessions
            WHERE active = 1
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

        if not row:
            return None

        conn.execute(
            """
            UPDATE focus_sessions
            SET active = 0, stopped_at = ?
            WHERE id = ?
            """,
            (now.isoformat(timespec="seconds"), row[0]),
        )
        conn.commit()

    return row[1]


def pop_due_focus_notice():
    now = datetime.now(TIMEZONE)

    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, label, ends_at
            FROM focus_sessions
            WHERE active = 1
              AND notified = 0
              AND ends_at <= ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (now.isoformat(timespec="seconds"),),
        ).fetchone()

        if not row:
            return None

        conn.execute(
            """
            UPDATE focus_sessions
            SET active = 0,
                notified = 1,
                stopped_at = ?
            WHERE id = ?
            """,
            (now.isoformat(timespec="seconds"), row[0]),
        )
        conn.commit()

    return {
        "id": row[0],
        "label": row[1],
        "ends_at": datetime.fromisoformat(row[2]),
    }


def parse_focus_start(text):
    lower = text.lower()

    if not any(
        phrase in lower
        for phrase in (
            "zacznij sesję",
            "zacznij sesje",
            "zacznij skupienie",
            "tryb skupienia",
            "pomodoro",
            "zacznij naukę",
            "zacznij nauke",
        )
    ):
        return None

    match = re.search(
        r"(\d{1,3})\s*(?:minut(?:ę|y)?|min)",
        lower,
    )
    minutes = int(match.group(1)) if match else 25

    if "program" in lower:
        label = "programowanie"
    elif "angiel" in lower:
        label = "angielski"
    elif "matem" in lower:
        label = "matematyka"
    else:
        label = "nauka"

    return {
        "minutes": max(1, min(minutes, 240)),
        "label": label,
    }


def format_focus_status():
    session = current_focus()

    if not session:
        return "Nie masz aktywnej sesji skupienia."

    if session["expired"]:
        return "Sesja skupienia właśnie się zakończyła."

    return (
        "Aktywna sesja "
        + session["label"]
        + ". Zostało około "
        + str(session["remaining_minutes"])
        + " minut."
    )
