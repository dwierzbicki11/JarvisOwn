"""Local study coach using only JARVIS-owned data.

The coach does not guess grades or mastery. It combines due flashcards,
study activity recency and upcoming study-like tasks into practical advice.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from skills.flashcards import list_cards, stats as flashcard_stats
from skills.focus import start_focus
from skills.study_progress import summary as study_summary
from skills.tasks import pending_tasks

STUDY_TASK_MARKERS = (
    "kolokw",
    "egzamin",
    "sprawozd",
    "laborator",
    "projekt",
    "nau",
    "powt",
    "matem",
    "program",
    "angiel",
    "zadanie",
    "ćwicz",
    "cwicz",
)


def _now(now=None):
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def _dt(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def neglected_subjects(limit=3, *, now=None):
    """Return subjects that are relatively stale or lightly practised."""
    rows = study_summary()
    if not rows:
        return []

    now = _now(now)
    scored = []

    for row in rows:
        last_at = _dt(row.get("last_at"))
        interactions = max(0, int(row.get("interactions", 0)))

        age_days = (
            max(0.0, (now - last_at).total_seconds() / 86400.0)
            if last_at
            else 365.0
        )

        # More age increases urgency, more practice decreases it slightly.
        score = age_days + 8.0 / max(1, interactions)

        scored.append(
            {
                "subject": row.get("subject", "ogólne"),
                "interactions": interactions,
                "age_days": round(age_days, 1),
                "score": score,
            }
        )

    scored.sort(
        key=lambda item: (
            -item["score"],
            item["subject"],
        )
    )
    return scored[: max(1, int(limit))]


def due_flashcard_summary(*, now=None):
    now = _now(now)
    cards = list_cards()
    due = []

    for card in cards:
        due_at = _dt(card.get("due_at"))
        if due_at and due_at <= now:
            due.append(card)

    due.sort(
        key=lambda card: (
            int(card.get("interval_days", 0)),
            int(card.get("reviews", 0)),
            int(card.get("id", 0)),
        )
    )

    return {
        "total": len(cards),
        "due": len(due),
        "examples": [
            str(card.get("question", "")).strip()
            for card in due[:3]
            if str(card.get("question", "")).strip()
        ],
    }


def upcoming_study_tasks(limit=3, *, now=None):
    now = _now(now)
    rows = pending_tasks(limit=30)
    result = []

    for task in rows:
        text = str(task.get("text", "")).strip()
        folded = text.lower()

        if not any(marker in folded for marker in STUDY_TASK_MARKERS):
            continue

        due_at = task.get("due_at")
        urgency_hours = None

        if due_at is not None:
            aware_due = due_at
            if aware_due.tzinfo is None:
                aware_due = aware_due.replace(tzinfo=timezone.utc)
            urgency_hours = round(
                (aware_due.astimezone(timezone.utc) - now).total_seconds()
                / 3600.0,
                1,
            )

        result.append(
            {
                "text": text,
                "due_at": due_at,
                "priority": bool(task.get("priority")),
                "urgency_hours": urgency_hours,
            }
        )

    result.sort(
        key=lambda item: (
            0 if item["priority"] else 1,
            (
                item["urgency_hours"]
                if item["urgency_hours"] is not None
                else 10**9
            ),
        )
    )
    return result[: max(1, int(limit))]


def build_snapshot(*, now=None):
    now = _now(now)
    cards = due_flashcard_summary(now=now)
    neglected = neglected_subjects(now=now)
    tasks = upcoming_study_tasks(now=now)

    return {
        "flashcards": cards,
        "neglected_subjects": neglected,
        "study_tasks": tasks,
    }


def format_recommendation(*, now=None):
    data = build_snapshot(now=now)
    parts = []

    cards = data["flashcards"]
    if cards["due"]:
        parts.append(
            f"Masz {cards['due']} fiszek do powtórki."
        )

    tasks = data["study_tasks"]
    if tasks:
        task = tasks[0]
        prefix = "Najpilniejsze zadanie edukacyjne to " if task["priority"] else "Najbliższe zadanie edukacyjne to "
        parts.append(prefix + task["text"] + ".")

    neglected = data["neglected_subjects"]
    if neglected:
        subject = neglected[0]["subject"]
        age = neglected[0]["age_days"]
        if age >= 1:
            parts.append(
                f"Warto też wrócić do obszaru {subject}, bo ostatnia aktywność była około {int(round(age))} dni temu."
            )
        else:
            parts.append(
                f"Do dodatkowej powtórki proponuję obszar {subject}."
            )

    if not parts:
        return (
            "Nie widzę teraz zaległych fiszek ani zapisanych zadań naukowych. "
            "Możemy zrobić krótką sesję z wybranego przedmiotu."
        )

    return " ".join(parts)


def build_study_plan(minutes=45, *, now=None):
    minutes = max(15, min(int(minutes), 180))
    data = build_snapshot(now=now)

    blocks = []
    remaining = minutes

    if data["flashcards"]["due"] and remaining >= 10:
        block = min(15, max(10, minutes // 4))
        blocks.append(("fiszki", block))
        remaining -= block

    tasks = data["study_tasks"]
    if tasks and remaining >= 15:
        block = min(30, max(15, remaining // 2))
        blocks.append((tasks[0]["text"], block))
        remaining -= block

    neglected = data["neglected_subjects"]
    if neglected and remaining >= 10:
        subject = neglected[0]["subject"]
        block = remaining
        blocks.append((f"powtórka: {subject}", block))
        remaining = 0

    if remaining > 0:
        blocks.append(("nauka wybranego bieżącego tematu", remaining))

    return {
        "minutes": minutes,
        "blocks": blocks,
    }


def format_study_plan(minutes=45, *, now=None):
    plan = build_study_plan(minutes=minutes, now=now)
    rendered = "; ".join(
        f"{label}: {block_minutes} minut"
        for label, block_minutes in plan["blocks"]
    )

    return (
        f"Plan nauki na {plan['minutes']} minut: "
        + rendered
        + "."
    )


def process_study_coach_command(text):
    lower = re.sub(r"\s+", " ", (text or "").lower()).strip()

    if any(
        phrase in lower
        for phrase in (
            "zacznij plan nauki",
            "uruchom plan nauki",
            "zacznij inteligentną sesję nauki",
            "zacznij inteligentna sesje nauki",
        )
    ):
        match = re.search(
            r"(\d{1,3})\s*(?:minut|min)",
            lower,
        )
        minutes = int(match.group(1)) if match else 45
        plan_text = format_study_plan(minutes)
        session = start_focus(
            minutes,
            label="plan nauki",
        )
        return (
            plan_text
            + " Uruchomiłem sesję skupienia na "
            + str(session["minutes"])
            + " minut."
        )

    if any(
        phrase in lower
        for phrase in (
            "co mam dziś powtórzyć",
            "co mam dzis powtorzyc",
            "czego mam się dziś uczyć",
            "czego mam sie dzis uczyc",
            "co powinienem dziś powtórzyć",
            "co powinienem dzis powtorzyc",
            "co dziś powtórzyć",
            "co dzis powtorzyc",
        )
    ):
        return format_recommendation()

    if any(
        phrase in lower
        for phrase in (
            "słabe tematy",
            "slabe tematy",
            "co zaniedbałem",
            "co zaniedbalem",
            "zaniedbane tematy",
            "obszary do powtórki",
            "obszary do powtorki",
        )
    ):
        rows = neglected_subjects(limit=3)

        if not rows:
            return "Nie mam jeszcze dość danych o aktywności nauki."

        return (
            "Obszary, do których warto wrócić na podstawie lokalnej aktywności: "
            + "; ".join(
                f"{row['subject']} — około {int(round(row['age_days']))} dni od ostatniej aktywności"
                for row in rows
            )
            + "."
        )

    if (
        "zaplanuj mi" in lower
        and "nauk" in lower
    ) or (
        "plan nauki" in lower
    ):
        match = re.search(
            r"(\d{1,3})\s*(?:minut|min)",
            lower,
        )
        minutes = int(match.group(1)) if match else 45
        return format_study_plan(minutes)

    return None
