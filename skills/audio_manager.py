import os
import re
import subprocess
import time
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path.home() / "jarvis"
load_dotenv(BASE_DIR / ".env")

BT_AUDIO_NAME = os.getenv(
    "BT_AUDIO_NAME",
    "Redmi Buds 6 Active",
).strip()

BT_DEVICE_MAC = os.getenv(
    "BT_DEVICE_MAC",
    "24:B2:31:81:7B:05",
).strip()

MIC_TARGET = os.getenv(
    "MIC_TARGET",
    f"bluez_input.{BT_DEVICE_MAC}",
).strip()

BT_FORCE_MSBC = os.getenv(
    "BT_FORCE_MSBC",
    "1",
) == "1"

BT_SETTLE_SECONDS = float(
    os.getenv(
        "BT_SETTLE_SECONDS",
        "0.35",
    )
)


def _run(command, timeout=6):
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _wpctl_status():
    result = _run(
        ["wpctl", "status"],
        timeout=5,
    )
    return result.stdout


def bluetooth_connected():
    if not BT_DEVICE_MAC:
        return False

    result = _run(
        [
            "bluetoothctl",
            "info",
            BT_DEVICE_MAC,
        ],
        timeout=5,
    )

    return (
        result.returncode == 0
        and "Connected: yes" in result.stdout
    )


def ensure_bluetooth_connected():
    if bluetooth_connected():
        return True

    if not BT_DEVICE_MAC:
        return False

    print(
        f"🎧 Łączenie z {BT_AUDIO_NAME}...",
        flush=True,
    )

    _run(
        [
            "bluetoothctl",
            "trust",
            BT_DEVICE_MAC,
        ],
        timeout=5,
    )

    result = _run(
        [
            "bluetoothctl",
            "connect",
            BT_DEVICE_MAC,
        ],
        timeout=12,
    )

    if "Connection successful" in result.stdout:
        time.sleep(BT_SETTLE_SECONDS)
        return True

    return bluetooth_connected()


def _find_section_id(
    section_name,
    display_name=None,
    node_name=None,
):
    status = _wpctl_status()
    active = False

    for raw in status.splitlines():
        line = raw.strip()

        if line.endswith(f"{section_name}:"):
            active = True
            continue

        if active and re.match(
            r"^(Devices|Sinks|Sources|Filters|Streams):$",
            line,
        ):
            break

        if not active:
            continue

        wanted = False

        if display_name and display_name in line:
            wanted = True

        if node_name and node_name in line:
            wanted = True

        if wanted:
            match = re.search(
                r"(?:\*\s*)?(\d+)\.\s+",
                line,
            )

            if match:
                return int(match.group(1))

    return None


def device_id():
    return _find_section_id(
        "Devices",
        display_name=BT_AUDIO_NAME,
    )


def sink_id():
    return _find_section_id(
        "Sinks",
        display_name=BT_AUDIO_NAME,
    )


def source_id():
    # W PipeWire mikrofon BT może występować jako Source albo Filter.
    source = _find_section_id(
        "Sources",
        display_name=BT_AUDIO_NAME,
    )

    if source is not None:
        return source

    return _find_section_id(
        "Filters",
        node_name=f"bluez_input.{BT_DEVICE_MAC}",
    )


def _profile_index(dev_id, profile_name):
    """
    Zwraca indeks profilu PipeWire z EnumProfile.

    Nie dzielimy outputu po "Object:", bo ten tekst występuje też
    wewnątrz nazw pól Spa:Pod:Object:Param:* i rozcinał poprzedni parser.
    """
    result = _run(
        [
            "pw-cli",
            "enum-params",
            str(dev_id),
            "EnumProfile",
        ],
        timeout=5,
    )

    if result.returncode != 0:
        return None

    pattern = re.compile(
        r"Profile:index.*?\n\s+Int\s+(\d+)"
        r".*?Profile:name.*?\n\s+String\s+\"([^\"]+)\"",
        flags=re.DOTALL,
    )

    for match in pattern.finditer(result.stdout):
        index = int(match.group(1))
        name = match.group(2)

        if name == profile_name:
            return index

    return None


def active_profile(dev_id):
    """
    Zwraca informacje o faktycznie aktywnym profilu urządzenia.
    """
    result = _run(
        [
            "pw-cli",
            "enum-params",
            str(dev_id),
            "Profile",
        ],
        timeout=5,
    )

    if result.returncode != 0:
        return None

    index_match = re.search(
        r"Profile:index.*?\n\s+Int\s+(\d+)",
        result.stdout,
        flags=re.DOTALL,
    )
    name_match = re.search(
        r"Profile:name.*?\n\s+String\s+\"([^\"]+)\"",
        result.stdout,
        flags=re.DOTALL,
    )
    desc_match = re.search(
        r"Profile:description.*?\n\s+String\s+\"([^\"]+)\"",
        result.stdout,
        flags=re.DOTALL,
    )

    if not name_match:
        return None

    description = (
        desc_match.group(1)
        if desc_match
        else name_match.group(1)
    )

    return {
        "index": (
            int(index_match.group(1))
            if index_match
            else None
        ),
        "name": name_match.group(1),
        "description": description,
        "msbc": "msbc" in description.lower(),
    }


def force_msbc():
    if not BT_FORCE_MSBC:
        return True

    dev_id = device_id()

    if dev_id is None:
        return False

    profile_index = _profile_index(
        dev_id,
        "headset-head-unit",
    )

    if profile_index is None:
        print(
            "⚠️ Nie znalazłem profilu HFP/mSBC.",
            flush=True,
        )
        return False

    result = _run(
        [
            "wpctl",
            "set-profile",
            str(dev_id),
            str(profile_index),
        ],
        timeout=5,
    )

    if result.returncode != 0:
        print(
            "[AUDIO] Nie udało się ustawić mSBC: "
            + result.stderr.strip(),
            flush=True,
        )
        return False

    time.sleep(BT_SETTLE_SECONDS)

    active = active_profile(dev_id)

    if not active:
        print(
            "⚠️ Ustawiono profil HFP, ale nie udało się odczytać "
            "aktywnego profilu.",
            flush=True,
        )
        return True

    if active["name"] != "headset-head-unit":
        print(
            "⚠️ PipeWire nie utrzymał profilu HFP: "
            + active["description"],
            flush=True,
        )
        return False

    return True


def set_defaults():
    sink = sink_id()
    source = source_id()

    if sink is not None:
        _run(
            [
                "wpctl",
                "set-default",
                str(sink),
            ]
        )
        _run(
            [
                "wpctl",
                "set-mute",
                str(sink),
                "0",
            ]
        )

    if source is not None:
        _run(
            [
                "wpctl",
                "set-default",
                str(source),
            ]
        )
        _run(
            [
                "wpctl",
                "set-mute",
                str(source),
                "0",
            ]
        )

    return sink, source


def prepare_audio():
    """
    Przygotowuje słuchawki przy starcie JARVIS-a.
    Nie używa stałych ID PipeWire, bo zmieniają się po reconnect.
    """
    if not ensure_bluetooth_connected():
        print(
            "⚠️ Słuchawki Bluetooth nie są połączone.",
            flush=True,
        )
        return False

    msbc_requested = BT_FORCE_MSBC
    msbc_set = force_msbc()

    # Zmiana profilu tworzy nowe nody, więc chwilę czekamy.
    time.sleep(BT_SETTLE_SECONDS)

    sink, source = set_defaults()
    dev_id = device_id()
    profile = active_profile(dev_id) if dev_id is not None else None

    if profile:
        codec_status = (
            "mSBC=active"
            if profile["msbc"]
            else f"profile={profile['description']}"
        )
    elif msbc_requested:
        codec_status = (
            "mSBC=unverified"
            if msbc_set
            else "mSBC=failed"
        )
    else:
        codec_status = "mSBC=disabled"

    print(
        "🎧 Audio: "
        f"sink={sink}, source={source}, "
        f"mic={MIC_TARGET}, "
        f"{codec_status}",
        flush=True,
    )

    return source is not None


def playback_target():
    """
    Zwraca aktualny sink jako tekst tylko na czas pojedynczego pw-play.
    Nie zapisujemy ID na stałe, bo po reconnect może się zmienić.
    """
    sink = sink_id()
    return str(sink) if sink is not None else None


def wait_after_playback():
    # HFP potrzebuje chwili zanim capture znów będzie stabilny.
    time.sleep(BT_SETTLE_SECONDS)
