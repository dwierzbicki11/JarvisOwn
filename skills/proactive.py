import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from skills.pk_calendar import get_first_class

TIMEZONE = ZoneInfo("Europe/Warsaw")
STATE_FILE = Path.home() / "jarvis" / "data" / "proactive_state.json"
STATE_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state):
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(STATE_FILE)


def class_notification_due():
    """
    Lekka, lokalna logika: jeśli pierwsze dzisiejsze zajęcia zaczynają
    się za 45-60 minut, zgłoś informację tylko raz.
    """
    now = datetime.now(TIMEZONE)
    event = get_first_class(0)

    if not event:
        return None

    delta = event["start"] - now

    if not timedelta(minutes=45) <= delta <= timedelta(minutes=60):
        return None

    key = (
        event["start"].isoformat()
        + "|"
        + event["summary"]
    )

    state = _load_state()

    if state.get("last_class_notice") == key:
        return None

    state["last_class_notice"] = key
    _save_state(state)

    minutes = max(1, round(delta.total_seconds() / 60))

    text = (
        f"Za około {minutes} minut masz "
        f"{event['summary']} o "
        f"{event['start'].strftime('%H:%M')}"
    )

    if event["location"]:
        text += f", {event['location']}"

    return text + "."
