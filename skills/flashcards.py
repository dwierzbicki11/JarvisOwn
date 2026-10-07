"""Offline flashcards with explicit self-assessment and durable review state."""
from contextlib import contextmanager
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path.home() / 'jarvis' / 'data' / 'jarvis.db'


def _now(now=None):
    return (now or datetime.now(timezone.utc)).astimezone(timezone.utc)


@contextmanager
def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS flashcards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            due_at TEXT NOT NULL,
            interval_days INTEGER NOT NULL DEFAULT 0,
            reviews INTEGER NOT NULL DEFAULT 0,
            UNIQUE(question, answer)
        );
        CREATE TABLE IF NOT EXISTS flashcard_session (
            singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
            card_id INTEGER,
            revealed INTEGER NOT NULL DEFAULT 0
        );
        INSERT OR IGNORE INTO flashcard_session(singleton) VALUES(1);
    ''')
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def add_card(question, answer, now=None):
    question, answer = _validate(question, answer)
    with _connect() as conn:
        conn.execute('INSERT OR IGNORE INTO flashcards(question, answer, due_at) VALUES(?, ?, ?)',
                     (question, answer, _now(now).isoformat()))
        return conn.execute('SELECT id FROM flashcards WHERE question=? AND answer=?',
                            (question, answer)).fetchone()['id']


def stats(now=None):
    with _connect() as conn:
        row = conn.execute('SELECT COUNT(*) AS total, COALESCE(SUM(due_at <= ?), 0) AS due, COALESCE(SUM(reviews), 0) AS reviews FROM flashcards',
                           (_now(now).isoformat(),)).fetchone()
        return dict(row)


def next_question(now=None):
    with _connect() as conn:
        # Preserve a pending question across restarts and repeated commands.
        row = conn.execute('SELECT f.* FROM flashcard_session s JOIN flashcards f ON f.id=s.card_id WHERE s.singleton=1').fetchone()
        if row is None:
            row = conn.execute('SELECT * FROM flashcards WHERE due_at <= ? ORDER BY due_at, id LIMIT 1',
                               (_now(now).isoformat(),)).fetchone()
            if row is None:
                return 'Nie ma teraz fiszek do powtórki.'
            conn.execute('UPDATE flashcard_session SET card_id=?, revealed=0 WHERE singleton=1', (row['id'],))
        return f"Fiszka {row['id']}: {row['question']} Powiedz: pokaż odpowiedź fiszki."


def reveal_answer():
    with _connect() as conn:
        row = conn.execute('SELECT f.answer FROM flashcard_session s JOIN flashcards f ON f.id=s.card_id WHERE s.singleton=1').fetchone()
        if row is None:
            return 'Najpierw powiedz: powtórka fiszek.'
        conn.execute('UPDATE flashcard_session SET revealed=1 WHERE singleton=1')
        return row['answer'] + ' Oceń swoją odpowiedź: fiszka pamiętam albo fiszka nie pamiętam.'


def review(remembered, now=None):
    with _connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT f.*, s.revealed FROM flashcard_session s JOIN flashcards f ON f.id=s.card_id WHERE s.singleton=1').fetchone()
        if row is None:
            return 'Nie ma aktywnej fiszki. Powiedz: powtórka fiszek.'
        if not row['revealed']:
            return 'Najpierw sprawdź odpowiedź: pokaż odpowiedź fiszki.'
        days = min(60, max(1, row['interval_days'] * 2)) if remembered else 0
        due = _now(now) + (timedelta(days=days) if remembered else timedelta(minutes=10))
        conn.execute('UPDATE flashcards SET due_at=?, interval_days=?, reviews=reviews+1 WHERE id=?',
                     (due.isoformat(), days, row['id']))
        conn.execute('UPDATE flashcard_session SET card_id=NULL, revealed=0 WHERE singleton=1')
        return (f'Zapisano. Powtórka za {days} dni.' if remembered else 'Zapisano. Powtórka za 10 minut.')


def process_flashcard_command(text):
    lower = re.sub(r'\s+', ' ', text.lower()).strip().rstrip('.!?')
    if lower.startswith(('dodaj fiszkę', 'dodaj fiszke')):
        match = re.fullmatch(r'dodaj fiszk[ęe]\s+(.+?)\s+odpowied[źz]\s+(.+)', text.strip(), re.I | re.S)
        if not match:
            return 'Powiedz: dodaj fiszkę, pytanie, odpowiedź, treść odpowiedzi. Na przykład: dodaj fiszkę ile to dwa plus dwa odpowiedź cztery.'
        try:
            card_id = add_card(match[1].strip(' ,'), match[2].strip(' ,'))
        except ValueError as exc:
            return str(exc)
        return f'Fiszka {card_id} zapisana.'
    if lower in ('powtórka fiszek', 'powtorka fiszek', 'następna fiszka', 'nastepna fiszka'):
        return next_question()
    if lower in ('pokaż odpowiedź fiszki', 'pokaz odpowiedz fiszki'):
        return reveal_answer()
    if lower == 'fiszka pamiętam' or lower == 'fiszka pamietam':
        return review(True)
    if lower == 'fiszka nie pamiętam' or lower == 'fiszka nie pamietam':
        return review(False)
    if lower in ('status fiszek', 'ile mam fiszek'):
        data = stats()
        return f"Masz {data['total']} fiszek, w tym {data['due']} do powtórki. Wykonano {data['reviews']} powtórek."
    if lower in ('koniec fiszek', 'zakończ fiszki', 'zakoncz fiszki'):
        with _connect() as conn:
            conn.execute('UPDATE flashcard_session SET card_id=NULL, revealed=0 WHERE singleton=1')
        return 'Powtórka fiszek zakończona.'
    return None


def _validate(question, answer):
    question, answer = question.strip(), answer.strip()
    if not question or not answer or len(question) > 1000 or len(answer) > 4000:
        raise ValueError('Podaj pytanie do 1000 znaków i odpowiedź do 4000 znaków.')
    return question, answer


def list_cards():
    with _connect() as conn:
        return [dict(row) for row in conn.execute('SELECT * FROM flashcards ORDER BY id DESC')]


def edit_card(card_id, question, answer, now=None):
    question, answer = _validate(question, answer)
    with _connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        try:
            result = conn.execute('UPDATE flashcards SET question=?, answer=?, due_at=?, interval_days=0 WHERE id=?',
                                  (question, answer, _now(now).isoformat(), card_id))
        except sqlite3.IntegrityError:
            raise ValueError('Taka fiszka już istnieje.')
        # An edited answer must be revealed again before grading.
        conn.execute('UPDATE flashcard_session SET revealed=0 WHERE card_id=?', (card_id,))
        return result.rowcount > 0


def delete_card(card_id):
    with _connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        result = conn.execute('DELETE FROM flashcards WHERE id=?', (card_id,))
        conn.execute('UPDATE flashcard_session SET card_id=NULL, revealed=0 WHERE card_id=?', (card_id,))
        return result.rowcount > 0
