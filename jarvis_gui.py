import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

import psutil
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from skills.conversation_history import recent_turns
from skills.audio_manager import bluetooth_battery
from skills.krakow_transport import next_departures
from skills.pk_calendar import get_first_class
from skills.proactive import proactive_status
from skills.reminders import pending_reminders
from skills.system_health import raid_status, wifi_status
from skills.study_rag import index_status as study_index_status
from skills.web_commands import submit_command

BASE_DIR = Path.home() / "jarvis"
load_dotenv(BASE_DIR / ".env")

STATE_FILE = BASE_DIR / "runtime" / "state.json"
HTML_FILE = BASE_DIR / "gui" / "index.html"

HOME_STOP = os.getenv(
    "JARVIS_HOME_STOP",
    "Garlica Duchowna Kapliczka",
)

WEATHER_LAT = float(
    os.getenv(
        "WEATHER_LAT",
        "50.0647",
    )
)

WEATHER_LON = float(
    os.getenv(
        "WEATHER_LON",
        "19.9450",
    )
)

app = FastAPI(
    docs_url=None,
    redoc_url=None,
)

cache = {}


class CommandRequest(BaseModel):
    text: str


def cached(
    name,
    ttl,
    function,
):
    now = time.monotonic()
    old = cache.get(name)

    if (
        old
        and now - old["time"] < ttl
    ):
        return old["value"]

    try:
        value = function()

        cache[name] = {
            "time": now,
            "value": value,
        }

        return value

    except Exception as exc:
        print(
            f"[GUI CACHE {name}] {exc}",
            flush=True,
        )

        return (
            old["value"]
            if old
            else None
        )


def jarvis_state():
    default = {
        "state": "offline",
        "last_user": "",
        "last_answer": "",
        "study_mode": None,
        "exam_mode": False,
        "last_latency": {},
        "speaker": {},
        "updated": 0,
    }

    if not STATE_FILE.exists():
        return default

    try:
        data = json.loads(
            STATE_FILE.read_text(
                encoding="utf-8"
            )
        )

        updated = float(
            data.get(
                "updated",
                0,
            )
        )

        if (
            updated
            and time.time() - updated > 45
        ):
            data["state"] = "offline"

        return {
            **default,
            **data,
        }

    except Exception:
        return default


WEATHER_CODES = {
    0: "Bezchmurnie",
    1: "Pogodnie",
    2: "Częściowe zachmurzenie",
    3: "Pochmurno",
    45: "Mgła",
    48: "Mgła",
    51: "Lekka mżawka",
    53: "Mżawka",
    55: "Silna mżawka",
    61: "Lekki deszcz",
    63: "Deszcz",
    65: "Silny deszcz",
    71: "Lekki śnieg",
    73: "Śnieg",
    75: "Silny śnieg",
    80: "Przelotny deszcz",
    81: "Przelotne opady",
    82: "Silne opady",
    95: "Burza",
    96: "Burza z gradem",
    99: "Silna burza",
}


def weather_data():
    response = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": WEATHER_LAT,
            "longitude": WEATHER_LON,
            "current": (
                "temperature_2m,"
                "apparent_temperature,"
                "weather_code"
            ),
            "timezone": "Europe/Warsaw",
        },
        timeout=8,
    )

    response.raise_for_status()
    current = response.json()["current"]

    return {
        "temperature": round(
            current["temperature_2m"]
        ),
        "apparent": round(
            current["apparent_temperature"]
        ),
        "description": WEATHER_CODES.get(
            current["weather_code"],
            "Brak danych",
        ),
    }


def next_class_data():
    for day_offset in range(
        0,
        8,
    ):
        event = get_first_class(
            day_offset
        )

        if not event:
            continue

        return {
            "summary": event["summary"],
            "time": event[
                "start"
            ].strftime("%H:%M"),
            "date": event[
                "start"
            ].strftime("%d.%m"),
            "location": event[
                "location"
            ],
        }

    return None


def temperature():
    try:
        return round(
            int(
                Path(
                    "/sys/class/thermal/"
                    "thermal_zone0/temp"
                ).read_text().strip()
            )
            / 1000
        )

    except Exception:
        return None


def system_data():
    return {
        "cpu": round(
            psutil.cpu_percent(
                interval=0.1
            )
        ),
        "ram": round(
            psutil.virtual_memory().percent
        ),
        "disk": round(
            psutil.disk_usage("/").percent
        ),
        "temp": temperature(),
    }


def docker_data():
    try:
        result = subprocess.check_output(
            [
                "docker",
                "ps",
                "--format",
                "{{.Names}}",
            ],
            text=True,
            timeout=4,
        )

        names = [
            line.strip()
            for line in result.splitlines()
            if line.strip()
        ]

        return {
            "running": len(names),
            "names": names,
        }

    except Exception:
        return {
            "running": 0,
            "names": [],
        }


def pihole_data():
    try:
        result = subprocess.run(
            [
                "systemctl",
                "is-active",
                "pihole-FTL",
            ],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
        )

        if (
            result.stdout.strip()
            == "active"
        ):
            return True

    except Exception:
        pass

    docker = docker_data()

    return any(
        "pihole" in name.lower()
        for name in docker["names"]
    )


def reminder_data():
    items = pending_reminders(
        limit=5
    )

    return [
        {
            "id": item["id"],
            "time": item[
                "due_at"
            ].strftime(
                "%d.%m %H:%M"
            ),
            "text": item["text"],
        }
        for item in items
    ]


@app.get("/")
def index():
    return HTMLResponse(
        HTML_FILE.read_text(
            encoding="utf-8"
        )
    )


@app.get("/health")
def health():
    return {
        "ok": True,
    }


@app.post("/api/command")
def command(request: CommandRequest):
    text = request.text.strip()

    if not text:
        raise HTTPException(
            status_code=400,
            detail="Puste polecenie.",
        )

    command_id = submit_command(text)

    if command_id is None:
        raise HTTPException(
            status_code=400,
            detail="Nie udało się zapisać polecenia.",
        )

    return {
        "ok": True,
        "id": command_id,
        "text": text,
    }


@app.get("/api/status")
def status():
    return {
        "jarvis": jarvis_state(),
        "history": recent_turns(
            limit=8
        ),
        "clock": {
            "time": datetime.now().strftime(
                "%H:%M:%S"
            ),
            "date": datetime.now().strftime(
                "%d.%m.%Y"
            ),
        },
        "weather": cached(
            "weather",
            300,
            weather_data,
        ),
        "class": cached(
            "class",
            120,
            next_class_data,
        ),
        "transport": cached(
            "transport",
            60,
            lambda: next_departures(
                HOME_STOP,
                limit=3,
            ),
        ),
        "reminders": cached(
            "reminders",
            5,
            reminder_data,
        ),
        "system": system_data(),
        "network": cached(
            "network",
            5,
            wifi_status,
        ),
        "raid": cached(
            "raid",
            5,
            raid_status,
        ),
        "services": cached(
            "services",
            15,
            lambda: {
                "docker": docker_data(),
                "pihole": pihole_data(),
            },
        ),
        "study": cached(
            "study",
            30,
            study_index_status,
        ),
        "headphones": cached(
            "headphones",
            10,
            bluetooth_battery,
        ),
        "proactive": cached(
            "proactive",
            30,
            proactive_status,
        ),
    }
