"""On-demand local analytics for JARVIS.

SQLite remains the source of truth. Pandas/NumPy are loaded only when an
analytics command is requested, so the normal voice loop does not pay their
startup/RAM cost on Raspberry Pi.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_DIR = Path.home() / "jarvis"
DATA_DIR = BASE_DIR / "data"
FOCUS_DB_PATH = DATA_DIR / "jarvis.db"
LEARNING_DB_PATH = DATA_DIR / "user_learning.sqlite3"
STUDY_DB_PATH = DATA_DIR / "study_progress.db"
TIMEZONE = ZoneInfo("Europe/Warsaw")


def _pandas():
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError(
            "Brak biblioteki pandas. Uruchom: "
            "python -m pip install -r ~/jarvis/requirements.txt"
        ) from exc
    return pd


def _numpy():
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            "Brak biblioteki numpy. Uruchom: "
            "python -m pip install -r ~/jarvis/requirements.txt"
        ) from exc
    return np


def _read_sql(path, query, columns):
    pd = _pandas()
    path = Path(path)

    if not path.exists():
        return pd.DataFrame(columns=columns)

    try:
        with sqlite3.connect(path, timeout=10) as conn:
            return pd.read_sql_query(query, conn)
    except (sqlite3.Error, ValueError):
        return pd.DataFrame(columns=columns)


def _local_timestamp_series(series):
    pd = _pandas()
    parsed = pd.to_datetime(
        series,
        utc=True,
        errors="coerce",
    )
    return parsed.dt.tz_convert(TIMEZONE)


def _normalized_now(now=None):
    if now is None:
        return datetime.now(TIMEZONE)

    if now.tzinfo is None:
        return now.replace(tzinfo=TIMEZONE)

    return now.astimezone(TIMEZONE)


def _top_counts(frame, column, value_name, limit=5):
    if frame.empty or column not in frame:
        return []

    values = (
        frame[column]
        .fillna("")
        .astype(str)
        .str.strip()
        .replace("", "ogólne")
    )

    counts = (
        values.value_counts()
        .head(max(1, min(int(limit), 20)))
    )

    return [
        {
            "value": str(index),
            value_name: int(count),
        }
        for index, count in counts.items()
    ]


def build_report(days=7, *, now=None):
    """Build a compact analytics snapshot from local SQLite databases."""
    pd = _pandas()
    np = _numpy()

    days = max(1, min(int(days), 365))
    now = _normalized_now(now)
    period_start = now - timedelta(days=days)
    now_ts = pd.Timestamp(now)
    start_ts = pd.Timestamp(period_start)

    events = _read_sql(
        LEARNING_DB_PATH,
        """
        SELECT created_at, route, subject
        FROM query_events
        """,
        ["created_at", "route", "subject"],
    )

    if not events.empty:
        events["created_at"] = _local_timestamp_series(
            events["created_at"]
        )
        events = events[
            events["created_at"].notna()
            & (events["created_at"] >= start_ts)
            & (events["created_at"] <= now_ts)
        ].copy()

    focus = _read_sql(
        FOCUS_DB_PATH,
        """
        SELECT label, started_at, ends_at, stopped_at, active
        FROM focus_sessions
        """,
        [
            "label",
            "started_at",
            "ends_at",
            "stopped_at",
            "active",
        ],
    )

    if not focus.empty:
        for column in (
            "started_at",
            "ends_at",
            "stopped_at",
        ):
            focus[column] = _local_timestamp_series(
                focus[column]
            )

        focus["effective_end"] = (
            focus["stopped_at"]
            .where(
                focus["stopped_at"].notna(),
                focus["ends_at"],
            )
        )

        focus = focus[
            focus["started_at"].notna()
            & focus["effective_end"].notna()
            & (focus["started_at"] <= now_ts)
            & (focus["effective_end"] >= start_ts)
        ].copy()

        if not focus.empty:
            effective_start = (
                focus["started_at"]
                .where(
                    focus["started_at"] >= start_ts,
                    start_ts,
                )
            )
            effective_end = (
                focus["effective_end"]
                .where(
                    focus["effective_end"] <= now_ts,
                    now_ts,
                )
            )
            focus["minutes"] = (
                (
                    effective_end
                    - effective_start
                )
                .dt.total_seconds()
                .div(60.0)
                .clip(lower=0.0, upper=240.0)
            )
            focus = focus[
                focus["minutes"] > 0
            ].copy()

    study = _read_sql(
        STUDY_DB_PATH,
        """
        SELECT subject, interactions, last_at
        FROM study_activity
        """,
        ["subject", "interactions", "last_at"],
    )

    if study.empty:
        lifetime_interactions = 0
        lifetime_subjects = []
    else:
        interactions = (
            pd.to_numeric(
                study["interactions"],
                errors="coerce",
            )
            .fillna(0)
            .clip(lower=0)
        )
        study = study.copy()
        study["interactions"] = interactions

        lifetime_interactions = int(
            interactions.sum()
        )

        lifetime_subjects = [
            {
                "value": str(row["subject"]),
                "interactions": int(
                    row["interactions"]
                ),
            }
            for _, row in (
                study
                .sort_values(
                    "interactions",
                    ascending=False,
                )
                .head(5)
                .iterrows()
            )
        ]

    if focus.empty:
        focus_minutes = 0.0
        focus_sessions = 0
        average_focus_minutes = 0.0
        focus_subjects = []
    else:
        durations = (
            focus["minutes"]
            .to_numpy(dtype=float)
        )

        focus_minutes = float(
            np.sum(durations)
        )
        focus_sessions = int(
            len(durations)
        )
        average_focus_minutes = float(
            np.mean(durations)
        )

        grouped_focus = (
            focus.assign(
                label=(
                    focus["label"]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .replace("", "nauka")
                )
            )
            .groupby(
                "label",
                dropna=False,
            )["minutes"]
            .sum()
            .sort_values(
                ascending=False
            )
            .head(5)
        )

        focus_subjects = [
            {
                "value": str(label),
                "minutes": float(minutes),
            }
            for label, minutes in grouped_focus.items()
        ]

    return {
        "period_days": days,
        "period_start": period_start.isoformat(
            timespec="seconds"
        ),
        "period_end": now.isoformat(
            timespec="seconds"
        ),
        "questions": int(len(events)),
        "question_subjects": _top_counts(
            events,
            "subject",
            "questions",
        ),
        "routes": _top_counts(
            events,
            "route",
            "count",
        ),
        "focus_sessions": focus_sessions,
        "focus_minutes": round(
            focus_minutes,
            1,
        ),
        "average_focus_minutes": round(
            average_focus_minutes,
            1,
        ),
        "focus_subjects": focus_subjects,
        "lifetime_study_interactions": (
            lifetime_interactions
        ),
        "lifetime_subjects": lifetime_subjects,
    }


def _format_minutes(value):
    total = max(
        0,
        int(round(float(value))),
    )
    hours, minutes = divmod(
        total,
        60,
    )

    if hours and minutes:
        return (
            f"{hours} godz. {minutes} min"
        )

    if hours:
        return f"{hours} godz."

    return f"{minutes} min"


def _format_top(items, count_key, *, limit=3):
    if not items:
        return "brak danych"

    parts = []

    for item in items[:limit]:
        value = item["value"]
        count = item[count_key]

        if count_key == "minutes":
            rendered = _format_minutes(
                count
            )
        else:
            rendered = str(
                int(count)
            )

        parts.append(
            f"{value}: {rendered}"
        )

    return ", ".join(parts)


def format_report(days=7, *, now=None):
    report = build_report(
        days=days,
        now=now,
    )

    parts = [
        (
            "Analityka JARVIS-a z ostatnich "
            f"{report['period_days']} dni."
        ),
        (
            "Pytania i komendy: "
            f"{report['questions']}."
        ),
        (
            "Sesje skupienia: "
            f"{report['focus_sessions']}, "
            "łącznie "
            f"{_format_minutes(report['focus_minutes'])}, "
            "średnio "
            f"{_format_minutes(report['average_focus_minutes'])}."
        ),
    ]

    if report["question_subjects"]:
        parts.append(
            "Najczęstsze tematy pytań: "
            + _format_top(
                report["question_subjects"],
                "questions",
            )
            + "."
        )

    if report["focus_subjects"]:
        parts.append(
            "Najwięcej czasu skupienia: "
            + _format_top(
                report["focus_subjects"],
                "minutes",
            )
            + "."
        )

    if report["lifetime_study_interactions"]:
        parts.append(
            "Łącznie zapisanych interakcji edukacyjnych: "
            f"{report['lifetime_study_interactions']}."
        )

    return " ".join(parts)


def _days_from_command(text):
    lower = (text or "").lower()

    match = re.search(
        r"(?:ostatni(?:e|ch)?\s+)?(\d{1,3})\s*dni",
        lower,
    )

    if match:
        return max(
            1,
            min(
                int(match.group(1)),
                365,
            ),
        )

    if "dzisiaj" in lower or "dziś" in lower:
        return 1

    if "miesiąc" in lower or "miesiac" in lower:
        return 30

    if (
        "tydzień" in lower
        or "tydzien" in lower
        or "w tym tygodniu" in lower
    ):
        return 7

    return 7


def process_analytics_command(text):
    lower = (text or "").lower().strip()

    markers = (
        "analityka jarvisa",
        "analitykę jarvisa",
        "analityke jarvisa",
        "raport nauki",
        "raport z nauki",
        "statystyki nauki",
        "podsumowanie nauki",
        "jak mi szła nauka",
        "jak mi szla nauka",
        "ile czasu się uczyłem",
        "ile czasu sie uczylem",
    )

    if not any(
        marker in lower
        for marker in markers
    ):
        return None

    try:
        return format_report(
            days=_days_from_command(
                lower
            )
        )
    except RuntimeError as exc:
        return str(exc)
