import json
import os
from pathlib import Path

import psutil
from dotenv import load_dotenv

from skills.system_health import raid_status

BASE_DIR = Path.home() / "jarvis"
load_dotenv(BASE_DIR / ".env")

STATE_FILE = BASE_DIR / "data" / "health_alert_state.json"
STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

HEALTH_ALERTS_ENABLED = os.getenv(
    "HEALTH_ALERTS_ENABLED",
    "1",
) == "1"

CPU_TEMP_ALERT_C = float(
    os.getenv(
        "CPU_TEMP_ALERT_C",
        "80",
    )
)

DISK_ALERT_PERCENT = float(
    os.getenv(
        "DISK_ALERT_PERCENT",
        "90",
    )
)

RAM_ALERT_PERCENT = float(
    os.getenv(
        "RAM_ALERT_PERCENT",
        "95",
    )
)


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


def _cpu_temperature():
    try:
        return (
            int(
                Path(
                    "/sys/class/thermal/"
                    "thermal_zone0/temp"
                ).read_text().strip()
            )
            / 1000.0
        )
    except Exception:
        return None


def _conditions():
    result = {}

    raid = raid_status()

    if (
        raid.get(
            "present"
        )
        and not raid.get(
            "healthy"
        )
    ):
        if raid.get(
            "progress"
        ) is not None:
            text = (
                "RAID "
                + str(
                    raid.get(
                        "name",
                        "",
                    )
                )
                + " nie jest jeszcze w pełni zdrowy. "
                + "Odbudowa ma "
                + f"{raid['progress']:.0f} procent."
            )
        else:
            text = (
                "Uwaga. RAID "
                + str(
                    raid.get(
                        "name",
                        "",
                    )
                )
                + " jest zdegradowany."
            )

        result[
            "raid"
        ] = text

    temperature = _cpu_temperature()

    if (
        temperature is not None
        and temperature
        >= CPU_TEMP_ALERT_C
    ):
        result[
            "cpu_temperature"
        ] = (
            "Uwaga. Temperatura Raspberry Pi jest wysoka: "
            f"{temperature:.0f} stopni."
        )

    disk = psutil.disk_usage(
        "/"
    ).percent

    if disk >= DISK_ALERT_PERCENT:
        result[
            "disk"
        ] = (
            "Uwaga. Dysk systemowy jest zajęty w "
            f"{disk:.0f} procentach."
        )

    ram = psutil.virtual_memory().percent

    if ram >= RAM_ALERT_PERCENT:
        result[
            "ram"
        ] = (
            "Uwaga. Wykorzystanie pamięci RAM wynosi "
            f"{ram:.0f} procent."
        )

    return result


def health_alert_due():
    """
    Zwraca tylko nowy problem. Ten sam problem nie jest powtarzany,
    dopóki stan nie wróci do normy i nie wystąpi ponownie.
    """
    if not HEALTH_ALERTS_ENABLED:
        return None

    current = _conditions()
    state = _load_state()

    active = set(
        state.get(
            "active",
            [],
        )
    )

    current_keys = set(
        current
    )

    # Problemy, które zniknęły, są odblokowane na przyszłość.
    active &= current_keys

    new_keys = [
        key
        for key in (
            "raid",
            "cpu_temperature",
            "disk",
            "ram",
        )
        if (
            key in current
            and key not in active
        )
    ]

    if not new_keys:
        state[
            "active"
        ] = sorted(
            active
        )
        _save_state(
            state
        )
        return None

    key = new_keys[0]
    active.add(
        key
    )

    state[
        "active"
    ] = sorted(
        active
    )

    _save_state(
        state
    )

    return current[
        key
    ]
