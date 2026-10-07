"""Local, privacy-preserving behavior learning.

Only aggregate topics, routes and short keyword counters are stored. Raw
questions already belong to conversation history; this module does not copy
them into another service or database table.
"""
import re
import sqlite3
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path.home() / "jarvis" / "data" / "user_learning.sqlite3"
STOPWORDS = {
    "ale", "czy", "co", "czemu", "dlaczego", "gdzie", "jaki", "jaka",
    "jakie", "jak", "jest", "mam", "mi", "mnie", "moje", "moich", "na",
    "nie", "oraz", "po", "pod", "się", "sie", "to", "w", "z", "ze",
}


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS query_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            route TEXT NOT NULL,
            subject TEXT,
            keywords TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS counters (
            kind TEXT NOT NULL,
            value TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(kind, value)
        )
        """
    )
    return conn


def _fold(text):
    value = unicodedata.normalize("NFKD", text or "").lower().replace("ł", "l")
    return "".join(char for char in value if not unicodedata.combining(char))


def keywords(text, limit=8):
    words = [
        word for word in re.findall(r"[a-z0-9ąćęłńóśźż+#.-]{3,}", _fold(text))
        if word not in STOPWORDS and not word.isdigit()
    ]
    return [word for word, _ in Counter(words).most_common(limit)]


def record_query(text, *, route="conversation", subject=None):
    text = (text or "").strip()
    if not text:
        return False
    terms = keywords(text)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _connect() as conn:
        conn.execute(
            "INSERT INTO query_events(created_at, route, subject, keywords) VALUES (?, ?, ?, ?)",
            (now, route, subject or "", " ".join(terms)),
        )
        for kind, value in (("route", route), ("subject", subject or "ogólne"), *(('keyword', term) for term in terms)):
            conn.execute(
                """
                INSERT INTO counters(kind, value, count) VALUES (?, ?, 1)
                ON CONFLICT(kind, value) DO UPDATE SET count = counters.count + 1
                """,
                (kind, value),
            )
    return True


def _top(conn, kind, limit=5):
    return [
        {"value": row[0], "count": row[1]}
        for row in conn.execute(
            "SELECT value, count FROM counters WHERE kind=? ORDER BY count DESC, value LIMIT ?",
            (kind, max(1, min(int(limit), 20))),
        ).fetchall()
    ]


def profile():
    with _connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM query_events").fetchone()[0]
        return {
            "enabled": True,
            "questions": int(total),
            "subjects": _top(conn, "subject"),
            "routes": _top(conn, "route"),
            "keywords": _top(conn, "keyword"),
        }


def context():
    data = profile()
    if not data["questions"]:
        return ""
    subjects = ", ".join(item["value"] for item in data["subjects"][:3])
    routes = ", ".join(item["value"] for item in data["routes"][:3])
    keywords_text = ", ".join(item["value"] for item in data["keywords"][:6])
    return (
        "Obserwowane lokalnie wzorce (to wskazówki, nie pewne fakty): "
        f"najczęstsze obszary: {subjects}; typy rozmów: {routes}; "
        f"powtarzające się słowa: {keywords_text}. "
        "Dopasuj poziom wyjaśnienia, ale nie zakładaj intencji użytkownika bez pytania."
    )


def clear():
    with _connect() as conn:
        conn.execute("DELETE FROM query_events")
        conn.execute("DELETE FROM counters")
    return True


def format_profile():
    data = profile()
    if not data["questions"]:
        return "Nie mam jeszcze wystarczającej liczby obserwacji."
    subjects = ", ".join(f"{x['value']} ({x['count']})" for x in data["subjects"][:5])
    routes = ", ".join(f"{x['value']} ({x['count']})" for x in data["routes"][:5])
    return f"Na podstawie {data['questions']} pytań najczęstsze obszary to: {subjects}. Typy rozmów: {routes}."


def process_learning_command(text):
    lower = _fold(text).strip()
    if any(phrase in lower for phrase in ("czego sie nauczyles", "co wiesz o moich nawykach", "profil moich pytan", "status uczenia")):
        return format_profile()
    if any(phrase in lower for phrase in ("wyczysc moje zachowania", "wyczysc profil uczenia", "zapomnij moje zachowania")):
        clear()
        return "Wyczyściłem lokalny profil obserwowanych zachowań."
    return None
