import os
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import recurring_ical_events
import requests
from dotenv import load_dotenv
from icalendar import Calendar

load_dotenv(Path.home() / "jarvis" / ".env")

TIMEZONE = ZoneInfo("Europe/Warsaw")
ICS_URL = os.getenv("PK_CALENDAR_ICS_URL", "").strip()


def _ensure_datetime(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=TIMEZONE)
        return value.astimezone(TIMEZONE)

    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=TIMEZONE)

    raise TypeError(f"Nieobsługiwany czas iCal: {type(value)}")


def _calendar():
    if not ICS_URL:
        raise RuntimeError("Brak PK_CALENDAR_ICS_URL w .env")

    response = requests.get(ICS_URL, timeout=15)
    response.raise_for_status()
    return Calendar.from_ical(response.content)


def _events_between(start, end):
    cal = _calendar()
    items = recurring_ical_events.of(cal).between(start, end)
    result = []

    for event in items:
        dtstart = _ensure_datetime(event["DTSTART"].dt)

        if "DTEND" in event:
            dtend = _ensure_datetime(event["DTEND"].dt)
        else:
            dtend = dtstart

        result.append(
            {
                "start": dtstart,
                "end": dtend,
                "summary": str(event.get("SUMMARY", "Zajęcia")).strip(),
                "location": str(event.get("LOCATION", "")).strip(),
            }
        )

    result.sort(key=lambda item: item["start"])
    return result


def get_schedule(day_offset=0):
    now = datetime.now(TIMEZONE)
    target = now.date() + timedelta(days=day_offset)
    start = datetime.combine(target, time.min, tzinfo=TIMEZONE)
    end = start + timedelta(days=1)

    try:
        events = _events_between(start, end)
    except Exception as exc:
        return f"Nie mogę pobrać planu zajęć. {exc}"

    if not events:
        return "Nie masz tego dnia zajęć w kalendarzu."

    prefix = "Jutro masz" if day_offset == 1 else "Masz"
    parts = []

    for event in events:
        text = (
            f"{event['summary']} od "
            f"{event['start'].strftime('%H:%M')} do "
            f"{event['end'].strftime('%H:%M')}"
        )

        if event["location"]:
            text += f", {event['location']}"

        parts.append(text)

    return prefix + ": " + "; ".join(parts) + "."


def get_first_class(day_offset=0):
    now = datetime.now(TIMEZONE)
    target = now.date() + timedelta(days=day_offset)
    start = datetime.combine(target, time.min, tzinfo=TIMEZONE)
    end = start + timedelta(days=1)

    try:
        events = _events_between(start, end)
    except Exception:
        return None

    if day_offset == 0:
        events = [
            event
            for event in events
            if event["end"] >= now
        ]

    return events[0] if events else None


def get_next_class():
    for offset in range(0, 14):
        event = get_first_class(offset)

        if not event:
            continue

        when = (
            "dzisiaj"
            if offset == 0
            else "jutro"
            if offset == 1
            else event["start"].strftime("%d.%m")
        )

        text = (
            f"Najbliższe zajęcia masz {when}: "
            f"{event['summary']} o {event['start'].strftime('%H:%M')}"
        )

        if event["location"]:
            text += f", {event['location']}"

        return text + "."

    return "Nie widzę najbliższych zajęć w kalendarzu."
