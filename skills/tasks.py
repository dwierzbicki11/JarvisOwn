import re
import sqlite3
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TIMEZONE = ZoneInfo("Europe/Warsaw")
DB_PATH = Path.home() / "jarvis" / "data" / "jarvis.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _connect():
    conn = sqlite3.connect(
        DB_PATH,
        timeout=10,
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            due_at TEXT,
            priority INTEGER NOT NULL DEFAULT 0,
            done INTEGER NOT NULL DEFAULT 0,
            notified INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            completed_at TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_tasks_pending
        ON tasks(done, due_at, priority, id)
        """
    )

    conn.commit()
    return conn


def add_task(
    text,
    *,
    due_at=None,
    priority=0,
):
    text = (text or "").strip().strip(" .")

    if not text:
        return None

    if due_at is not None:
        due_at = due_at.astimezone(
            TIMEZONE
        ).isoformat(
            timespec="seconds"
        )

    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO tasks(
                text,
                due_at,
                priority,
                done,
                notified,
                created_at
            )
            VALUES(?, ?, ?, 0, 0, ?)
            """,
            (
                text,
                due_at,
                int(bool(priority)),
                datetime.now(
                    TIMEZONE
                ).isoformat(
                    timespec="seconds"
                ),
            ),
        )
        conn.commit()
        return cursor.lastrowid


def pending_tasks(
    limit=10,
):
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, text, due_at, priority, created_at
            FROM tasks
            WHERE done = 0
            ORDER BY
                CASE WHEN due_at IS NULL THEN 1 ELSE 0 END,
                due_at ASC,
                priority DESC,
                id ASC
            LIMIT ?
            """,
            (
                int(limit),
            ),
        ).fetchall()

    return [
        {
            "id": row[0],
            "text": row[1],
            "due_at": (
                datetime.fromisoformat(
                    row[2]
                )
                if row[2]
                else None
            ),
            "priority": bool(
                row[3]
            ),
            "created_at": (
                datetime.fromisoformat(
                    row[4]
                )
            ),
        }
        for row in rows
    ]


def complete_latest():
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, text
            FROM tasks
            WHERE done = 0
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

        if not row:
            return None

        conn.execute(
            """
            UPDATE tasks
            SET done = 1,
                completed_at = ?
            WHERE id = ?
            """,
            (
                datetime.now(
                    TIMEZONE
                ).isoformat(
                    timespec="seconds"
                ),
                row[0],
            ),
        )
        conn.commit()

    return row[1]


def delete_latest():
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, text
            FROM tasks
            WHERE done = 0
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

        if not row:
            return None

        conn.execute(
            "DELETE FROM tasks WHERE id = ?",
            (
                row[0],
            ),
        )
        conn.commit()

    return row[1]


WEEKDAY_ALIASES = {
    0: (
        "poniedzialek",
        "poniedzialku",
    ),
    1: (
        "wtorek",
        "wtorku",
    ),
    2: (
        "sroda",
        "srode",
        "srody",
    ),
    3: (
        "czwartek",
        "czwartku",
    ),
    4: (
        "piatek",
        "piatku",
    ),
    5: (
        "sobota",
        "sobote",
        "soboty",
    ),
    6: (
        "niedziela",
        "niedziele",
        "niedzieli",
    ),
}


def _normalize_words(text):
    value = unicodedata.normalize(
        "NFKD",
        (text or "").lower(),
    )

    value = "".join(
        char
        for char in value
        if not unicodedata.combining(
            char
        )
    )

    value = value.translate(
        str.maketrans(
            {
                "ł": "l",
                "Ł": "L",
            }
        )
    )

    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


def _requested_weekday(text):
    normalized = _normalize_words(
        text
    )

    words = set(
        re.findall(
            r"[a-z]+",
            normalized,
        )
    )

    for weekday, aliases in WEEKDAY_ALIASES.items():
        if any(
            alias in words
            for alias in aliases
        ):
            return weekday

    return None


def _weekday_date(
    now,
    weekday,
    *,
    hour,
    minute,
):
    days = (
        weekday
        - now.weekday()
    ) % 7

    target = (
        now.date()
        + timedelta(
            days=days
        )
    )

    candidate = datetime(
        target.year,
        target.month,
        target.day,
        hour,
        minute,
        tzinfo=TIMEZONE,
    )

    if candidate <= now:
        candidate += timedelta(
            days=7
        )

    return candidate


def _parse_time(
    raw,
):
    match = re.search(
        r"\b([01]?\d|2[0-3])(?::|\.)([0-5]\d)\b",
        raw,
    )

    if not match:
        return None

    return (
        int(
            match.group(1)
        ),
        int(
            match.group(2)
        ),
    )


def parse_task_command(
    text,
):
    """
    Przykłady:
      dodaj zadanie zrobić sprawozdanie
      dodaj zadanie na jutro o 18:00 zrobić sprawozdanie
      dodaj pilne zadanie kupić baterie
    """
    raw = text.strip()
    lower = raw.lower()

    if not (
        lower.startswith(
            "dodaj zadanie"
        )
        or lower.startswith(
            "dodaj nowe zadanie"
        )
        or lower.startswith(
            "dodaj pilne zadanie"
        )
        or lower.startswith(
            "dodaj ważne zadanie"
        )
        or lower.startswith(
            "dodaj wazne zadanie"
        )
    ):
        return None

    priority = (
        "pilne" in lower
        or "ważne" in lower
        or "wazne" in lower
    )

    body = re.sub(
        r"^dodaj\s+(?:nowe\s+)?"
        r"(?:(?:pilne|ważne|wazne)\s+)?"
        r"zadanie\s*",
        "",
        raw,
        count=1,
        flags=re.IGNORECASE,
    ).strip()

    now = datetime.now(
        TIMEZONE
    )
    due_at = None

    day_offset = None

    if re.search(
        r"\bpojutrze\b",
        body,
        flags=re.IGNORECASE,
    ):
        day_offset = 2

    elif re.search(
        r"\bjutro\b",
        body,
        flags=re.IGNORECASE,
    ):
        day_offset = 1

    elif re.search(
        r"\bdzis(?:iaj)?\b",
        body,
        flags=re.IGNORECASE,
    ):
        day_offset = 0

    weekday = _requested_weekday(
        body
    )

    time_value = _parse_time(
        body
    )

    hour, minute = (
        time_value
        if time_value is not None
        else (
            20,
            0,
        )
    )

    if day_offset is not None:
        target_date = (
            now.date()
            + timedelta(
                days=day_offset
            )
        )

        due_at = datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            hour,
            minute,
            tzinfo=TIMEZONE,
        )

    elif weekday is not None:
        due_at = _weekday_date(
            now,
            weekday,
            hour=hour,
            minute=minute,
        )

    elif time_value is not None:
        due_at = datetime(
            now.year,
            now.month,
            now.day,
            hour,
            minute,
            tzinfo=TIMEZONE,
        )

        if due_at <= now:
            due_at += timedelta(
                days=1
            )

    # Usuń fragment czasu z treści samego zadania.
    body = re.sub(
        r"\b(?:na\s+)?pojutrze\b",
        " ",
        body,
        flags=re.IGNORECASE,
    )
    body = re.sub(
        r"\b(?:na\s+)?jutro\b",
        " ",
        body,
        flags=re.IGNORECASE,
    )
    body = re.sub(
        r"\b(?:na\s+)?dzis(?:iaj)?\b",
        " ",
        body,
        flags=re.IGNORECASE,
    )
    body = re.sub(
        (
            r"\b(?:w|we|na)\s+"
            r"(?:poniedziałek|poniedzialek|poniedziałku|poniedzialku|"
            r"wtorek|wtorku|środę|srode|środa|sroda|"
            r"czwartek|czwartku|piątek|piatek|piątku|piatku|"
            r"sobotę|sobote|sobota|niedzielę|niedziele|niedziela)\b"
        ),
        " ",
        body,
        flags=re.IGNORECASE,
    )
    body = re.sub(
        r"\bo\s+([01]?\d|2[0-3])(?::|\.)([0-5]\d)\b",
        " ",
        body,
        flags=re.IGNORECASE,
    )
    body = re.sub(
        r"\b([01]?\d|2[0-3])(?::|\.)([0-5]\d)\b",
        " ",
        body,
    )
    body = re.sub(
        r"\s+",
        " ",
        body,
    ).strip(
        " ,.-"
    )

    if not body:
        return None

    return {
        "text": body,
        "due_at": due_at,
        "priority": priority,
    }


def format_pending(
    limit=7,
):
    tasks = pending_tasks(
        limit=limit
    )

    if not tasks:
        return (
            "Nie masz aktywnych zadań."
        )

    parts = []

    for task in tasks:
        prefix = (
            "pilne: "
            if task["priority"]
            else ""
        )

        text = (
            prefix
            + task["text"]
        )

        if task["due_at"]:
            text += (
                " do "
                + task[
                    "due_at"
                ].strftime(
                    "%d.%m %H:%M"
                )
            )

        parts.append(
            text
        )

    return (
        "Masz do zrobienia: "
        + "; ".join(
            parts
        )
        + "."
    )


def pop_due_task_notices(
    *,
    horizon_minutes=30,
    limit=5,
):
    """
    Zwraca zadania z terminem w ciągu N minut, tylko raz.
    """
    now = datetime.now(
        TIMEZONE
    )
    horizon = (
        now
        + timedelta(
            minutes=horizon_minutes
        )
    )

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, text, due_at, priority
            FROM tasks
            WHERE done = 0
              AND notified = 0
              AND due_at IS NOT NULL
              AND due_at <= ?
            ORDER BY due_at ASC
            LIMIT ?
            """,
            (
                horizon.isoformat(
                    timespec="seconds"
                ),
                int(limit),
            ),
        ).fetchall()

        ids = [
            row[0]
            for row in rows
        ]

        if ids:
            placeholders = ",".join(
                "?"
                for _ in ids
            )

            conn.execute(
                f"""
                UPDATE tasks
                SET notified = 1
                WHERE id IN ({placeholders})
                """,
                ids,
            )
            conn.commit()

    notices = []

    for row in rows:
        due = datetime.fromisoformat(
            row[2]
        )

        delta = round(
            (
                due - now
            ).total_seconds()
            / 60
        )

        notices.append(
            {
                "id": row[0],
                "text": row[1],
                "due_at": due,
                "priority": bool(
                    row[3]
                ),
                "minutes": delta,
            }
        )

    return notices
