import json
import os
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

BASE_DIR = Path.home() / "jarvis"
load_dotenv(BASE_DIR / ".env")

TIMEZONE = ZoneInfo("Europe/Warsaw")
STATE_FILE = BASE_DIR / "data" / "scheduled_briefings.json"
STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

BRIEFING_ENABLED = os.getenv(
    "BRIEFING_ENABLED",
    "1",
) == "1"

BRIEFING_MORNING_TIME = os.getenv(
    "BRIEFING_MORNING_TIME",
    "07:00",
)

BRIEFING_EVENING_TIME = os.getenv(
    "BRIEFING_EVENING_TIME",
    "21:00",
)

BRIEFING_CATCHUP_MINUTES = max(
    5,
    int(
        os.getenv(
            "BRIEFING_CATCHUP_MINUTES",
            "120",
        )
    ),
)


def _parse_clock(value):
    try:
        hour, minute = [
            int(part)
            for part in value.split(
                ":",
                1,
            )
        ]

        if not (
            0 <= hour <= 23
            and 0 <= minute <= 59
        ):
            raise ValueError

        return time(
            hour,
            minute,
        )
    except Exception:
        return None


def _load_state():
    try:
        return json.loads(
            STATE_FILE.read_text(
                encoding="utf-8",
            )
        )
    except Exception:
        return {}


def _save_state(state):
    tmp = STATE_FILE.with_suffix(
        ".tmp"
    )

    tmp.write_text(
        json.dumps(
            state,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    tmp.replace(
        STATE_FILE
    )


def _scheduled_datetime(
    now,
    clock_text,
):
    parsed = _parse_clock(
        clock_text
    )

    if parsed is None:
        return None

    return datetime.combine(
        now.date(),
        parsed,
        tzinfo=TIMEZONE,
    )


def briefing_due(
    *,
    now=None,
):
    """
    Zwraca "today" albo "tomorrow" tylko raz dziennie
    w krótkim oknie po skonfigurowanej godzinie.

    Dzięki oknu catch-up restart Raspberry Pi kilka minut po godzinie
    nie powoduje utraty briefingu, ale start o południu nie odtwarza
    spóźnionego komunikatu z rana.
    """
    if not BRIEFING_ENABLED:
        return None

    now = now or datetime.now(
        TIMEZONE
    )

    state = _load_state()

    schedules = (
        (
            "morning",
            "today",
            BRIEFING_MORNING_TIME,
        ),
        (
            "evening",
            "tomorrow",
            BRIEFING_EVENING_TIME,
        ),
    )

    for key, kind, clock_text in schedules:
        scheduled = _scheduled_datetime(
            now,
            clock_text,
        )

        if scheduled is None:
            continue

        end = (
            scheduled
            + timedelta(
                minutes=BRIEFING_CATCHUP_MINUTES
            )
        )

        if not (
            scheduled
            <= now
            <= end
        ):
            continue

        state_key = (
            "last_"
            + key
            + "_date"
        )

        today_key = now.date().isoformat()

        if state.get(
            state_key
        ) == today_key:
            continue

        state[
            state_key
        ] = today_key

        _save_state(
            state
        )

        return kind

    return None


def briefing_status(
    *,
    now=None,
):
    now = now or datetime.now(
        TIMEZONE
    )

    result = {
        "enabled": BRIEFING_ENABLED,
        "morning_time": BRIEFING_MORNING_TIME,
        "evening_time": BRIEFING_EVENING_TIME,
        "next_kind": None,
        "next_at": None,
    }

    if not BRIEFING_ENABLED:
        return result

    candidates = []

    for kind, clock_text in (
        (
            "today",
            BRIEFING_MORNING_TIME,
        ),
        (
            "tomorrow",
            BRIEFING_EVENING_TIME,
        ),
    ):
        parsed = _parse_clock(
            clock_text
        )

        if parsed is None:
            continue

        when = datetime.combine(
            now.date(),
            parsed,
            tzinfo=TIMEZONE,
        )

        if when <= now:
            when += timedelta(
                days=1
            )

        candidates.append(
            (
                when,
                kind,
            )
        )

    if candidates:
        when, kind = min(
            candidates,
            key=lambda item: item[0],
        )

        result[
            "next_kind"
        ] = kind
        result[
            "next_at"
        ] = when.isoformat()

    return result
