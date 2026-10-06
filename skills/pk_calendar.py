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


def _normalize_subject(text):
    import unicodedata
    import re

    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(
        ch for ch in text
        if not unicodedata.combining(ch)
    )
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def find_subject_schedule(subject, days=120):
    """
    Szuka najbliższych wystąpień konkretnego przedmiotu
    w kalendarzu PK.
    """
    from difflib import SequenceMatcher

    subject_norm = _normalize_subject(subject)

    if not subject_norm:
        return "Nie podałeś nazwy przedmiotu."

    now = datetime.now(TIMEZONE)
    start = now
    end = now + timedelta(days=days)

    try:
        events = _events_between(start, end)
    except Exception as exc:
        return f"Nie mogę pobrać planu zajęć. {exc}"

    matches = []

    for event in events:
        summary = event["summary"]
        summary_norm = _normalize_subject(summary)

        score = SequenceMatcher(
            None,
            subject_norm,
            summary_norm,
        ).ratio()

        # Najlepiej działa dla:
        # "analiza matematyczna"
        # "analiza"
        # lekko przekręconej nazwy przez Whispera.
        if (
            subject_norm in summary_norm
            or summary_norm in subject_norm
            or score >= 0.58
        ):
            matches.append(
                (score, event)
            )

    if not matches:
        return (
            f"Nie znalazłem przedmiotu {subject} "
            "w twoim kalendarzu."
        )

    matches.sort(
        key=lambda item: (
            item[1]["start"],
            -item[0],
        )
    )

    weekdays = {
        0: "poniedziałek",
        1: "wtorek",
        2: "środę",
        3: "czwartek",
        4: "piątek",
        5: "sobotę",
        6: "niedzielę",
    }

    # Najbliższe trzy wystąpienia.
    selected = [
        item[1]
        for item in matches[:3]
    ]

    parts = []

    for event in selected:
        start_dt = event["start"]
        end_dt = event["end"]

        when = weekdays[
            start_dt.weekday()
        ]

        part = (
            f"{event['summary']} masz w {when}, "
            f"{start_dt.strftime('%d.%m')} "
            f"od {start_dt.strftime('%H:%M')} "
            f"do {end_dt.strftime('%H:%M')}"
        )

        if event["location"]:
            part += (
                f", {event['location']}"
            )

        parts.append(part)

    return (
        "Najbliższe terminy: "
        + "; ".join(parts)
        + "."
    )



_CALENDAR_STOPWORDS = {
    "a", "czy", "dla", "do", "i", "ja", "jak", "jaki", "jakie",
    "jakim", "jest", "kiedy", "ktorego", "ktory", "ktora", "mam",
    "mial", "miala", "mieli", "miec", "na", "o", "od", "po",
    "przedmiot", "przedmiotu", "sie", "ten", "tego", "to", "w",
    "we", "z", "za", "zajecia", "bede", "bedziemy", "najblizsze",
    "najblizszy", "dniu", "dzien", "godzinie", "godzina",
}


def _normalize_calendar_text(text):
    import re
    import unicodedata

    value = unicodedata.normalize(
        "NFKD",
        (text or "").lower(),
    )

    value = "".join(
        ch
        for ch in value
        if not unicodedata.combining(ch)
    )

    aliases = (
        (r"\blaboratori(?:um|a|ow|ach|ami)\b", " lab "),
        (r"\blaboratoryjn(?:e|y|a|ych|ego)\b", " lab "),
        (r"\blab(?:y|ach|ow)?\b", " lab "),
        (r"\bwyklad(?:y|ach|ow)?\b", " wyklad "),
        (r"\bcwiczeni(?:a|ach|ami)\b", " cwiczenia "),
        (r"\bprojekt(?:y|ach|ow)?\b", " projekt "),
        (r"\bseminari(?:um|a|ach)\b", " seminarium "),
    )

    for pattern, replacement in aliases:
        value = re.sub(
            pattern,
            replacement,
            value,
        )

    value = re.sub(
        r"[^a-z0-9+#\s-]",
        " ",
        value,
    )

    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


def _calendar_tokens(text):
    normalized = _normalize_calendar_text(text)

    return {
        token
        for token in normalized.split()
        if (
            token
            and token not in _CALENDAR_STOPWORDS
        )
    }


def _requested_activity(text):
    normalized = _normalize_calendar_text(text)

    for activity in (
        "lab",
        "wyklad",
        "cwiczenia",
        "projekt",
        "seminarium",
    ):
        if activity in normalized.split():
            return activity

    return None


def _looks_like_calendar_question(text):
    normalized = _normalize_calendar_text(text)

    direct_starts = (
        "kiedy mam ",
        "kiedy bede mial ",
        "kiedy bede miec ",
        "kiedy bedzie ",
        "kiedy jest ",
        "czy mam ",
        "czy bede mial ",
        "czy bede miec ",
        "gdzie mam ",
        "gdzie bede mial ",
        "gdzie bede miec ",
        "w jakiej sali mam ",
        "w jakiej sali bede mial ",
        "w jakiej sali bede miec ",
        "w jaki dzien mam ",
        "w jaki dzien bede mial ",
        "o ktorej mam ",
        "o ktorej bede mial ",
        "ktorego dnia mam ",
        "ktorego dnia bede mial ",
    )

    if normalized.startswith(direct_starts):
        return True

    academic_words = (
        "przedmiot",
        "zajecia",
        "lab",
        "wyklad",
        "cwiczenia",
        "projekt",
        "seminarium",
        "uczeln",
    )

    time_words = (
        "kiedy",
        "ktorego dnia",
        "o ktorej",
        "najblizsze",
    )

    return (
        any(word in normalized for word in academic_words)
        and any(word in normalized for word in time_words)
    )


def _subject_score(
    query_tokens,
    event_summary,
):
    from difflib import SequenceMatcher

    event_tokens = _calendar_tokens(
        event_summary
    )

    # Rodzaj zajęć oceniamy osobno.
    event_subject_tokens = {
        token
        for token in event_tokens
        if token not in {
            "lab",
            "wyklad",
            "cwiczenia",
            "projekt",
            "seminarium",
        }
    }

    query_subject_tokens = {
        token
        for token in query_tokens
        if token not in {
            "lab",
            "wyklad",
            "cwiczenia",
            "projekt",
            "seminarium",
        }
    }

    if not query_subject_tokens:
        return 0.70

    overlap = len(
        query_subject_tokens
        & event_subject_tokens
    )

    coverage = (
        overlap
        / max(
            1,
            len(query_subject_tokens),
        )
    )

    query_phrase = " ".join(
        sorted(query_subject_tokens)
    )
    event_phrase = " ".join(
        sorted(event_subject_tokens)
    )

    sequence = SequenceMatcher(
        None,
        query_phrase,
        event_phrase,
    ).ratio()

    return (
        coverage * 0.78
        + sequence * 0.22
    )


def _format_calendar_matches(
    events,
    activity=None,
):
    if not events:
        return None

    weekdays = {
        0: "poniedziałek",
        1: "wtorek",
        2: "środę",
        3: "czwartek",
        4: "piątek",
        5: "sobotę",
        6: "niedzielę",
    }

    activity_names = {
        "lab": "laboratorium",
        "wyklad": "wykład",
        "cwiczenia": "ćwiczenia",
        "projekt": "projekt",
        "seminarium": "seminarium",
    }

    parts = []

    for event in events[:3]:
        start_dt = event["start"]
        end_dt = event["end"]

        item = (
            f"{event['summary']} masz w "
            f"{weekdays[start_dt.weekday()]}, "
            f"{start_dt.strftime('%d.%m')} "
            f"od {start_dt.strftime('%H:%M')} "
            f"do {end_dt.strftime('%H:%M')}"
        )

        if event["location"]:
            item += (
                f", {event['location']}"
            )

        parts.append(item)

    prefix = (
        f"Najbliższe {activity_names[activity]}: "
        if activity in activity_names
        else "Najbliższe terminy: "
    )

    return prefix + "; ".join(parts) + "."


def answer_calendar_question(
    text,
    *,
    days=180,
    context_turns=None,
):
    """
    Odpowiada na naturalne pytania o konkretny przedmiot/typ zajęć.

    Zwraca:
      - tekst odpowiedzi, jeśli pytanie dotyczy kalendarza,
      - None, jeśli to nie wygląda na pytanie kalendarzowe.

    Dzięki temu pytania o prywatny plan nie trafiają do ogólnego LLM.
    """
    normalized = _normalize_calendar_text(text)

    looks_like_question = _looks_like_calendar_question(
        text
    )

    # Krótkie odwołanie do poprzedniej odpowiedzi, np.
    # "A laboratorium?", "A o której?", "A w jakiej sali?".
    if (
        not looks_like_question
        and context_turns
    ):
        followup_markers = (
            "lab",
            "wyklad",
            "cwiczenia",
            "projekt",
            "seminarium",
            "kiedy",
            "o ktorej",
            "gdzie",
            "w jakiej sali",
            "ktorego dnia",
        )

        short_followup = (
            len(normalized.split()) <= 7
            and (
                normalized.startswith("a ")
                or any(
                    marker in normalized
                    for marker in followup_markers
                )
            )
        )

        if short_followup:
            previous = " ".join(
                (
                    str(turn.get("user", ""))
                    + " "
                    + str(turn.get("assistant", ""))
                )
                for turn in context_turns[-3:]
            )

            previous_norm = _normalize_calendar_text(
                previous
            )

            looks_like_question = any(
                marker in previous_norm
                for marker in (
                    "zajecia",
                    "lab",
                    "wyklad",
                    "cwiczenia",
                    "masz w ",
                    " od ",
                    " do ",
                )
            )

    if not looks_like_question:
        return None

    # Nie przechwytuj domen obsługiwanych przez inne lokalne moduły.
    blocked = (
        "autobus",
        "tramwaj",
        "dojazd",
        "wyjsc z domu",
        "dojechac",
        "pogoda",
    )

    if any(word in normalized for word in blocked):
        return None

    now = datetime.now(TIMEZONE)
    end = now + timedelta(days=days)

    try:
        events = _events_between(
            now,
            end,
        )
    except Exception as exc:
        return (
            "Nie mogę teraz pobrać twojego "
            f"planu zajęć. {exc}"
        )

    if not events:
        return (
            "Nie widzę żadnych przyszłych "
            "zajęć w twoim kalendarzu."
        )

    activity = _requested_activity(text)
    query_tokens = _calendar_tokens(text)

    # Usuń słowa będące tylko rodzajem zajęć.
    pure_subject_tokens = {
        token
        for token in query_tokens
        if token not in {
            "lab",
            "wyklad",
            "cwiczenia",
            "projekt",
            "seminarium",
        }
    }

    # Krótkie follow-upy typu "a laboratorium?" używają
    # nazwy przedmiotu z ostatnich pytań użytkownika. Nie dokładamy
    # całej odpowiedzi JARVIS-a, bo daty/sale pogarszały dopasowanie.
    if (
        not pure_subject_tokens
        and context_turns
    ):
        for turn in reversed(
            context_turns[-3:]
        ):
            previous_tokens = _calendar_tokens(
                str(
                    turn.get(
                        "user",
                        "",
                    )
                )
            )

            previous_subject_tokens = {
                token
                for token in previous_tokens
                if (
                    token not in {
                        "lab",
                        "wyklad",
                        "cwiczenia",
                        "projekt",
                        "seminarium",
                    }
                    and not token.isdigit()
                )
            }

            if previous_subject_tokens:
                query_tokens |= (
                    previous_subject_tokens
                )
                break

    scored = []

    for event in events:
        event_norm = _normalize_calendar_text(
            event["summary"]
        )

        if (
            activity
            and activity not in event_norm.split()
        ):
            continue

        score = _subject_score(
            query_tokens,
            event["summary"],
        )

        scored.append(
            (
                score,
                event,
            )
        )

    if not scored:
        kind = (
            {
                "lab": "laboratorium",
                "wyklad": "wykładu",
                "cwiczenia": "ćwiczeń",
                "projekt": "projektu",
                "seminarium": "seminarium",
            }.get(
                activity,
                "takich zajęć",
            )
        )

        return (
            f"Nie znalazłem przyszłego {kind} "
            "pasującego do tego pytania "
            "w twoim kalendarzu."
        )

    scored.sort(
        key=lambda item: (
            -item[0],
            item[1]["start"],
        )
    )

    best_score = scored[0][0]

    # Gdy podano nazwę przedmiotu, nie zgaduj przy słabym dopasowaniu.
    if (
        pure_subject_tokens
        and best_score < 0.52
    ):
        return (
            "Nie znalazłem przedmiotu "
            "pasującego do tego pytania "
            "w twoim kalendarzu."
        )

    # Najpierw wybierz najlepszą nazwę przedmiotu, potem terminy.
    best_summary = scored[0][1]["summary"]
    best_summary_tokens = _calendar_tokens(
        best_summary
    )

    matching_events = []

    for score, event in scored:
        if score < max(
            0.52,
            best_score - 0.12,
        ):
            continue

        event_tokens = _calendar_tokens(
            event["summary"]
        )

        # Chroni przed zmieszaniem dwóch różnych przedmiotów
        # o częściowo podobnych nazwach.
        common = len(
            best_summary_tokens
            & event_tokens
        )
        similarity = (
            common
            / max(
                1,
                len(best_summary_tokens),
            )
        )

        if similarity >= 0.60:
            matching_events.append(event)

    matching_events.sort(
        key=lambda event: event["start"]
    )

    print(
        "🎯 INTENT calendar_subject "
        f"activity={activity or 'any'} "
        f"score={best_score:.2f} "
        f"summary={best_summary}",
        flush=True,
    )

    return _format_calendar_matches(
        matching_events,
        activity=activity,
    )
