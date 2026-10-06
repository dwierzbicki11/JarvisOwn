import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from skills.audio_manager import bluetooth_battery
from skills.pk_calendar import get_first_class
from skills.route_planner import (
    CLASS_BUFFER_MINUTES,
    HOME_STOP,
    HOME_WALK_MINUTES,
    PK_STOP,
    PK_WALK_MINUTES,
    find_journey,
)

BASE_DIR = Path.home() / "jarvis"
load_dotenv(BASE_DIR / ".env")

TIMEZONE = ZoneInfo("Europe/Warsaw")
STATE_FILE = BASE_DIR / "data" / "proactive_state.json"
STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

PROACTIVE_ENABLED = os.getenv(
    "PROACTIVE_ENABLED",
    "1",
) == "1"

PROACTIVE_CLASS_NOTICE_MINUTES = int(
    os.getenv(
        "PROACTIVE_CLASS_NOTICE_MINUTES",
        "60",
    )
)

PROACTIVE_PREP_NOTICE_MINUTES = int(
    os.getenv(
        "PROACTIVE_PREP_NOTICE_MINUTES",
        "30",
    )
)

PROACTIVE_LEAVE_WINDOW_MINUTES = int(
    os.getenv(
        "PROACTIVE_LEAVE_WINDOW_MINUTES",
        "6",
    )
)

PROACTIVE_PLAN_HORIZON_HOURS = int(
    os.getenv(
        "PROACTIVE_PLAN_HORIZON_HOURS",
        "6",
    )
)

PROACTIVE_ROUTE_CACHE_SECONDS = int(
    os.getenv(
        "PROACTIVE_ROUTE_CACHE_SECONDS",
        "300",
    )
)

PROACTIVE_HEADPHONES_LOW_PERCENT = int(
    os.getenv(
        "PROACTIVE_HEADPHONES_LOW_PERCENT",
        "20",
    )
)

PROACTIVE_HEADPHONES_CRITICAL_PERCENT = int(
    os.getenv(
        "PROACTIVE_HEADPHONES_CRITICAL_PERCENT",
        "10",
    )
)

_ROUTE_CACHE = {}


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


def _event_key(
    event,
    kind,
):
    return (
        kind
        + "|"
        + event["start"].isoformat()
        + "|"
        + event["summary"]
    )


def _claim_once(
    event,
    kind,
):
    """
    Zwraca True tylko przy pierwszym zgłoszeniu danego typu
    dla konkretnego wydarzenia.
    """
    state = _load_state()
    key = _event_key(
        event,
        kind,
    )

    notices = state.setdefault(
        "notices",
        {},
    )

    if notices.get(key):
        return False

    notices[key] = (
        datetime.now(
            TIMEZONE
        ).isoformat()
    )

    # Nie pozwól plikowi stanu rosnąć bez końca.
    if len(notices) > 80:
        newest = list(
            notices.items()
        )[-40:]

        state["notices"] = dict(
            newest
        )

    _save_state(
        state
    )
    return True


def _minutes(delta):
    return round(
        delta.total_seconds()
        / 60
    )


def commute_plan_for_first_class(
    *,
    now=None,
):
    """
    Wylicza realny plan wyjścia z domu dla najbliższych dzisiejszych zajęć.

    Korzysta z kalendarza PK i statycznego GTFS. Zwraca None, gdy nie ma
    dzisiejszych zajęć albo są zbyt daleko, żeby obciążać planner w tle.
    """
    if not PROACTIVE_ENABLED:
        return None

    now = now or datetime.now(
        TIMEZONE
    )

    event = get_first_class(
        0
    )

    if not event:
        return None

    until_class = (
        event["start"]
        - now
    )

    if until_class < timedelta(
        minutes=-5
    ):
        return None

    if until_class > timedelta(
        hours=PROACTIVE_PLAN_HORIZON_HOURS
    ):
        return {
            "event": event,
            "journey": None,
            "leave_home": None,
            "minutes_to_class": _minutes(
                until_class
            ),
        }

    latest_arrival = (
        event["start"]
        - timedelta(
            minutes=(
                PK_WALK_MINUTES
                + CLASS_BUFFER_MINUTES
            )
        )
    )

    route_key = (
        event["start"].isoformat()
        + "|"
        + event["summary"]
    )

    cached = _ROUTE_CACHE.get(
        route_key
    )

    if (
        cached
        and time.monotonic()
        - cached["time"]
        < PROACTIVE_ROUTE_CACHE_SECONDS
    ):
        journey = cached[
            "journey"
        ]
    else:
        journey = find_journey(
            target_date=event[
                "start"
            ].date(),
            origin_name=HOME_STOP,
            destination_name=PK_STOP,
            latest_arrival=latest_arrival,
        )

        _ROUTE_CACHE.clear()
        _ROUTE_CACHE[
            route_key
        ] = {
            "time": time.monotonic(),
            "journey": journey,
        }

    if (
        not journey
        or "error" in journey
    ):
        return {
            "event": event,
            "journey": journey,
            "leave_home": None,
            "minutes_to_class": _minutes(
                until_class
            ),
        }

    leave_home = (
        journey["departure"]
        - timedelta(
            minutes=HOME_WALK_MINUTES
        )
    )

    return {
        "event": event,
        "journey": journey,
        "leave_home": leave_home,
        "minutes_to_leave": _minutes(
            leave_home - now
        ),
        "minutes_to_class": _minutes(
            until_class
        ),
    }


def proactive_status():
    """
    Dane przeznaczone m.in. dla GUI.
    """
    plan = commute_plan_for_first_class()

    if not plan:
        return {
            "enabled": PROACTIVE_ENABLED,
            "active": False,
        }

    event = plan["event"]
    leave_home = plan.get(
        "leave_home"
    )

    result = {
        "enabled": PROACTIVE_ENABLED,
        "active": True,
        "class": {
            "summary": event[
                "summary"
            ],
            "start": event[
                "start"
            ].isoformat(),
            "time": event[
                "start"
            ].strftime(
                "%H:%M"
            ),
            "location": event.get(
                "location",
                "",
            ),
        },
        "minutes_to_class": plan.get(
            "minutes_to_class"
        ),
        "leave_home": (
            leave_home.isoformat()
            if leave_home
            else None
        ),
        "leave_time": (
            leave_home.strftime(
                "%H:%M"
            )
            if leave_home
            else None
        ),
        "minutes_to_leave": plan.get(
            "minutes_to_leave"
        ),
    }

    journey = plan.get(
        "journey"
    )

    if (
        journey
        and "error" not in journey
    ):
        first_leg = (
            journey.get(
                "legs",
                [],
            )
            or [{}]
        )[0]

        result["transport"] = {
            "route": first_leg.get(
                "route"
            ),
            "departure": (
                first_leg.get(
                    "departure"
                ).strftime(
                    "%H:%M"
                )
                if first_leg.get(
                    "departure"
                )
                else None
            ),
            "from": first_leg.get(
                "from"
            ),
        }

    elif journey and journey.get(
        "error"
    ):
        result["route_error"] = (
            journey["error"]
        )

    return result


def class_notification_due(
    *,
    now=None,
):
    """
    Proaktywne powiadomienia dla najbliższych zajęć.

    Priorytet:
      1. "wyjdź teraz" na podstawie GTFS,
      2. "za ~30 min wyjście",
      3. ogólne przypomnienie o zajęciach.

    Każdy typ powiadomienia dla danych zajęć jest emitowany tylko raz.
    """
    if not PROACTIVE_ENABLED:
        return None

    now = now or datetime.now(
        TIMEZONE
    )

    plan = commute_plan_for_first_class(
        now=now
    )

    if not plan:
        return None

    event = plan[
        "event"
    ]

    leave_home = plan.get(
        "leave_home"
    )

    if leave_home:
        until_leave = (
            leave_home - now
        )

        leave_minutes = _minutes(
            until_leave
        )

        # Najważniejszy komunikat: czas realnie wychodzić.
        if (
            -2
            <= leave_minutes
            <= PROACTIVE_LEAVE_WINDOW_MINUTES
        ):
            if _claim_once(
                event,
                "leave_now",
            ):
                journey = plan[
                    "journey"
                ]
                first_leg = (
                    journey.get(
                        "legs",
                        [],
                    )
                    or [{}]
                )[0]

                route = first_leg.get(
                    "route"
                )
                departure = first_leg.get(
                    "departure"
                )

                text = (
                    "Powinieneś już wychodzić z domu. "
                )

                if route and departure:
                    text += (
                        f"Linia {route} odjeżdża "
                        f"o {departure.strftime('%H:%M')}. "
                    )

                text += (
                    f"Zajęcia {event['summary']} "
                    f"zaczynają się o "
                    f"{event['start'].strftime('%H:%M')}."
                )

                return text

        prep_target = timedelta(
            minutes=(
                PROACTIVE_PREP_NOTICE_MINUTES
            )
        )

        # 5-minutowe okno pasuje do częstotliwości background worker.
        if (
            prep_target
            - timedelta(minutes=3)
            <= until_leave
            <= prep_target
            + timedelta(minutes=3)
        ):
            if _claim_once(
                event,
                "prepare",
            ):
                return (
                    "Za około "
                    f"{max(1, leave_minutes)} minut "
                    "powinieneś wyjść z domu na uczelnię. "
                    f"Najbliższe zajęcia to {event['summary']} "
                    f"o {event['start'].strftime('%H:%M')}."
                )

    until_class = (
        event["start"]
        - now
    )

    class_target = timedelta(
        minutes=(
            PROACTIVE_CLASS_NOTICE_MINUTES
        )
    )

    if (
        class_target
        - timedelta(minutes=3)
        <= until_class
        <= class_target
        + timedelta(minutes=3)
    ):
        if _claim_once(
            event,
            "class",
        ):
            minutes = max(
                1,
                _minutes(
                    until_class
                ),
            )

            text = (
                f"Za około {minutes} minut masz "
                f"{event['summary']} o "
                f"{event['start'].strftime('%H:%M')}"
            )

            if event.get(
                "location"
            ):
                text += (
                    f", {event['location']}"
                )

            return text + "."

    return None



def headphone_battery_notification_due():
    """
    Ostrzega raz przy wejściu w niski i krytyczny poziom baterii.
    Po naładowaniu powyżej progu stan ostrzeżenia resetuje się.
    """
    if not PROACTIVE_ENABLED:
        return None

    battery = bluetooth_battery()

    if (
        not battery.get(
            "connected"
        )
        or not battery.get(
            "available"
        )
    ):
        return None

    percentage = battery.get(
        "percentage"
    )

    if percentage is None:
        return None

    state = _load_state()
    battery_state = state.setdefault(
        "headphones_battery",
        {},
    )

    previous_tier = battery_state.get(
        "notified_tier"
    )

    if (
        percentage
        > PROACTIVE_HEADPHONES_LOW_PERCENT
        + 5
    ):
        if previous_tier is not None:
            battery_state[
                "notified_tier"
            ] = None
            battery_state[
                "last_level"
            ] = percentage
            _save_state(
                state
            )
        return None

    if (
        percentage
        <= PROACTIVE_HEADPHONES_CRITICAL_PERCENT
    ):
        tier = "critical"
    elif (
        percentage
        <= PROACTIVE_HEADPHONES_LOW_PERCENT
    ):
        tier = "low"
    else:
        return None

    battery_state[
        "last_level"
    ] = percentage

    if previous_tier == tier:
        _save_state(
            state
        )
        return None

    # Po ostrzeżeniu LOW pozwól później zgłosić CRITICAL.
    # Po CRITICAL nie cofamy się do LOW bez ponownego naładowania.
    if (
        previous_tier == "critical"
        and tier == "low"
    ):
        _save_state(
            state
        )
        return None

    battery_state[
        "notified_tier"
    ] = tier
    _save_state(
        state
    )

    if tier == "critical":
        return (
            "Uwaga. Bateria słuchawek jest krytycznie niska: "
            f"{percentage} procent."
        )

    return (
        "Bateria słuchawek jest niska: "
        f"{percentage} procent."
    )
