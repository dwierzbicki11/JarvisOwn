"""Durable tutoring state. Model calls happen outside database transactions."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

DB_PATH = Path.home() / "jarvis" / "data" / "study_sessions.sqlite3"
SUBJECTS = ("matematyka", "programowanie", "angielski")
MODES = ("quiz", "kroki", "naprowadzanie")
LEVELS = ("podstawowy", "średni", "zaawansowany")
GRADES = ("correct", "partial", "wrong", "ungraded")


class SessionError(ValueError):
    pass


@contextmanager
def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS tutoring_sessions (
                id INTEGER PRIMARY KEY,
                subject TEXT NOT NULL, goal TEXT NOT NULL,
                mode TEXT NOT NULL, level TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'active',
                exam INTEGER NOT NULL DEFAULT 0,
                version INTEGER NOT NULL DEFAULT 0,
                question TEXT NOT NULL DEFAULT '',
                feedback TEXT NOT NULL DEFAULT '',
                awaiting_answer INTEGER NOT NULL DEFAULT 0,
                questions INTEGER NOT NULL DEFAULT 0,
                correct INTEGER NOT NULL DEFAULT 0,
                partial INTEGER NOT NULL DEFAULT 0,
                wrong INTEGER NOT NULL DEFAULT 0,
                ungraded INTEGER NOT NULL DEFAULT 0,
                hints INTEGER NOT NULL DEFAULT 0,
                skipped INTEGER NOT NULL DEFAULT 0,
                started_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS one_open_tutoring_session
                ON tutoring_sessions((1)) WHERE state != 'finished';
            CREATE TABLE IF NOT EXISTS tutoring_turns (
                id INTEGER PRIMARY KEY,
                session_id INTEGER NOT NULL REFERENCES tutoring_sessions(id),
                action TEXT NOT NULL, user_text TEXT NOT NULL,
                feedback TEXT NOT NULL, grade TEXT NOT NULL,
                question TEXT NOT NULL, created_at TEXT NOT NULL
            );
        """)
        with conn:
            yield conn
    finally:
        conn.close()


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def current():
    with _connect() as conn:
        row = conn.execute("SELECT * FROM tutoring_sessions WHERE state != 'finished'").fetchone()
        return dict(row) if row else None


def recent(limit=10):
    with _connect() as conn:
        return [dict(row) for row in conn.execute(
            "SELECT * FROM tutoring_sessions ORDER BY id DESC LIMIT ?", (max(1, min(20, limit)),)
        )]


def history(session_id, limit=6):
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM tutoring_turns WHERE session_id=? ORDER BY id DESC LIMIT ?",
            (session_id, max(1, min(20, limit))),
        ).fetchall()
        return [dict(row) for row in reversed(rows)]


def start(subject, goal="", mode="quiz", level="podstawowy", exam=False):
    if subject not in SUBJECTS or mode not in MODES or level not in LEVELS:
        raise SessionError("Wybierz poprawny przedmiot, tryb i poziom.")
    if not isinstance(goal, str) or len(goal.strip()) > 500:
        raise SessionError("Cel nauki może mieć do 500 znaków.")
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT 1 FROM tutoring_sessions WHERE state != 'finished'").fetchone():
            raise SessionError("Sesja już trwa. Wznów ją albo zakończ przed rozpoczęciem nowej.")
        now = _now()
        cursor = conn.execute("""
            INSERT INTO tutoring_sessions(subject, goal, mode, level, exam, started_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (subject, goal.strip(), mode, level, int(exam), now, now))
        return dict(conn.execute("SELECT * FROM tutoring_sessions WHERE id=?", (cursor.lastrowid,)).fetchone())


def transition(action):
    states = {"pause": "paused", "resume": "active", "stop": "finished"}
    if action not in states:
        raise SessionError("Nieznana zmiana stanu sesji.")
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM tutoring_sessions WHERE state != 'finished'").fetchone()
        if not row:
            raise SessionError("Nie ma aktywnej sesji nauki.")
        conn.execute("UPDATE tutoring_sessions SET state=?, version=version+1, updated_at=? WHERE id=?",
                     (states[action], _now(), row["id"]))
        return dict(conn.execute("SELECT * FROM tutoring_sessions WHERE id=?", (row["id"],)).fetchone())


def configure(*, mode=None, exam=None):
    if mode is not None and mode not in MODES:
        raise SessionError("Nieznany tryb nauki.")
    with _connect() as conn:
        conn.execute("""UPDATE tutoring_sessions SET mode=COALESCE(?, mode),
            exam=COALESCE(?, exam), version=version+1, updated_at=? WHERE state != 'finished'""",
                     (mode, None if exam is None else int(exam), _now()))


def validate_reply(raw, action):
    if not isinstance(raw, str) or len(raw) > 16000:
        raise SessionError("Model zwrócił nieprawidłową odpowiedź. Spróbuj ponownie.")
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        raise SessionError("Model zwrócił nieprawidłowy format. Wynik nie został zmieniony.")
    if not isinstance(data, dict) or set(data) != {"feedback", "grade", "question"}:
        raise SessionError("Brak wymaganych pól odpowiedzi. Wynik nie został zmieniony.")
    for key in ("feedback", "question"):
        if not isinstance(data[key], str) or len(data[key]) > 4000:
            raise SessionError("Nieprawidłowa treść odpowiedzi modelu.")
        data[key] = data[key].strip()
    if data["grade"] not in GRADES:
        raise SessionError("Nieznana ocena modelu. Wynik nie został zmieniony.")
    if action in ("question", "skip"):
        if not data["question"] or data["grade"] != "ungraded":
            raise SessionError("Nowe pytanie nie może oceniać użytkownika.")
    elif action in ("answer", "hint"):
        if not data["feedback"] or data["question"]:
            raise SessionError("Oczekiwano informacji zwrotnej bez kolejnego pytania.")
        if action == "hint" and data["grade"] != "ungraded":
            raise SessionError("Podpowiedź nie może zmieniać wyniku.")
    else:
        raise SessionError("Nieznana akcja korepetytora.")
    return data


def save_reply(snapshot, action, user_text, raw):
    """Compare-and-swap prevents a late response from scoring a different turn."""
    reply = validate_reply(raw, action)
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM tutoring_sessions WHERE id=?", (snapshot["id"],)).fetchone()
        if not row or row["version"] != snapshot["version"] or row["state"] != "active":
            raise SessionError("Sesja zmieniła się w trakcie odpowiedzi. Odśwież jej status.")
        if action in ("answer", "hint", "skip") and not row["awaiting_answer"]:
            raise SessionError("Najpierw poproś o następne pytanie w sesji.")
        if action == "question" and row["awaiting_answer"]:
            raise SessionError("Najpierw odpowiedz lub pomiń bieżące pytanie.")
        question = reply["question"] if action in ("question", "skip") else row["question"]
        pending = (action in ("question", "skip", "hint") or
                   (action == "answer" and reply["grade"] == "ungraded"))
        conn.execute("""
            UPDATE tutoring_sessions SET question=?, feedback=?, awaiting_answer=?,
                questions=questions+?, hints=hints+?, skipped=skipped+?,
                correct=correct+?, partial=partial+?, wrong=wrong+?, ungraded=ungraded+?,
                version=version+1, updated_at=? WHERE id=?
        """, (question, reply["feedback"], int(pending),
              int(action in ("question", "skip")), int(action == "hint"), int(action == "skip"),
              *(int(action == "answer" and reply["grade"] == grade) for grade in GRADES),
              _now(), row["id"]))
        conn.execute("""INSERT INTO tutoring_turns
            (session_id, action, user_text, feedback, grade, question, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
                     (row["id"], action, user_text, reply["feedback"], reply["grade"], question, _now()))
    return reply


def format_status(row=None):
    row = current() if row is None else row
    if row is None:
        return "Nie ma aktywnej sesji nauki."
    graded = row["correct"] + row["partial"] + row["wrong"]
    return (
        f"Sesja {row['id']}: {row['subject']}, poziom {row['level']}, tryb {row['mode']}. "
        f"Stan: { {'active': 'aktywna', 'paused': 'wstrzymana', 'finished': 'zakończona'}[row['state']] }. "
        f"Ocenione odpowiedzi: {graded}; poprawne: {row['correct']}, częściowe: {row['partial']}, "
        f"błędne: {row['wrong']}. Podpowiedzi: {row['hints']}, pominięcia: {row['skipped']}. "
        "Oceny są sugestią modelu."
    )
