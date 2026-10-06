import re
import subprocess
from pathlib import Path


def _run(command, timeout=4):
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def wifi_status(interface="wlan0"):
    text = _run(
        ["iw", "dev", interface, "link"],
        timeout=4,
    )

    if not text or "Not connected" in text:
        return {
            "connected": False,
            "ssid": None,
            "freq_mhz": None,
            "band": None,
            "signal_dbm": None,
            "rx_mbps": None,
            "tx_mbps": None,
        }

    def find_float(pattern):
        match = re.search(pattern, text)
        return float(match.group(1)) if match else None

    ssid_match = re.search(r"SSID:\s*(.+)", text)
    freq = find_float(r"freq:\s*([0-9.]+)")
    signal = find_float(r"signal:\s*(-?[0-9.]+)\s*dBm")
    rx = find_float(r"rx bitrate:\s*([0-9.]+)\s*MBit/s")
    tx = find_float(r"tx bitrate:\s*([0-9.]+)\s*MBit/s")

    band = None

    if freq:
        if 2400 <= freq < 2500:
            band = "2.4 GHz"
        elif 4900 <= freq < 5900:
            band = "5 GHz"
        elif 5925 <= freq < 7125:
            band = "6 GHz"

    return {
        "connected": True,
        "ssid": ssid_match.group(1).strip() if ssid_match else None,
        "freq_mhz": freq,
        "band": band,
        "signal_dbm": signal,
        "rx_mbps": rx,
        "tx_mbps": tx,
    }


def raid_status():
    try:
        mdstat = Path("/proc/mdstat").read_text(encoding="utf-8")
    except Exception:
        mdstat = ""

    match = re.search(
        r"^(md\d+)\s*:\s*(.+?)(?:\n\n|\Z)",
        mdstat,
        flags=re.MULTILINE | re.DOTALL,
    )

    if not match:
        return {
            "present": False,
            "name": None,
            "state": None,
            "healthy": None,
            "progress": None,
            "speed_kbps": None,
        }

    name = match.group(1)
    block = match.group(2)

    state_match = re.search(r"\[([U_]+)\]", block)
    progress_match = re.search(
        r"(?:recovery|resync|reshape)\s*=\s*([0-9.]+)%",
        block,
    )
    speed_match = re.search(r"speed=([0-9]+)K/sec", block)

    state = state_match.group(1) if state_match else None

    return {
        "present": True,
        "name": name,
        "state": state,
        "healthy": state is not None and "_" not in state,
        "progress": (
            float(progress_match.group(1))
            if progress_match
            else None
        ),
        "speed_kbps": (
            int(speed_match.group(1))
            if speed_match
            else None
        ),
    }


def service_active(service):
    return _run(
        ["systemctl", "is-active", service],
        timeout=3,
    ) == "active"


def short_health_text():
    wifi = wifi_status()
    raid = raid_status()

    parts = []

    if wifi["connected"]:
        text = "Wi-Fi"

        if wifi["band"]:
            text += f" {wifi['band']}"

        if wifi["signal_dbm"] is not None:
            text += f", sygnał {round(wifi['signal_dbm'])} dBm"

        if wifi["rx_mbps"] is not None:
            text += f", odbiór {wifi['rx_mbps']:.1f} megabita"

        if wifi["tx_mbps"] is not None:
            text += f", wysyłanie {wifi['tx_mbps']:.1f} megabita"

        parts.append(text + ".")
    else:
        parts.append("Wi-Fi nie jest połączone.")

    if raid["present"]:
        if raid["healthy"]:
            parts.append(
                f"RAID {raid['name']} jest zdrowy, stan {raid['state']}."
            )
        elif raid["progress"] is not None:
            parts.append(
                f"RAID {raid['name']} odbudowuje się. "
                f"Postęp {raid['progress']:.1f} procent."
            )
        else:
            parts.append(
                f"RAID {raid['name']} jest zdegradowany, "
                f"stan {raid['state'] or 'nieznany'}."
            )

    return " ".join(parts)
