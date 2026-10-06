import os
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

from dotenv import load_dotenv

BASE = Path.home() / "jarvis"
sys.path.insert(0, str(BASE))
load_dotenv(BASE / ".env")

errors = []
warnings = []


def ok(message):
    print(f"✅ {message}")


def warn(message):
    warnings.append(message)
    print(f"⚠️ {message}")


def fail(message):
    errors.append(message)
    print(f"❌ {message}")


print("=== JARVIS SELFTEST ===")
print(f"Python: {sys.version.split()[0]}")

for package in (
    "groq",
    "piper-tts",
    "openwakeword",
    "webrtcvad-wheels",
    "fastapi",
    "uvicorn",
):
    try:
        ok(f"{package}: {version(package)}")
    except Exception:
        fail(f"brak pakietu {package}")

if os.getenv("GROQ_API_KEY"):
    ok("GROQ_API_KEY obecny")
else:
    fail("brak GROQ_API_KEY w .env")

voice = os.getenv(
    "TTS_VOICE",
    "pl_PL-mc_speech-medium",
)

voice_dir = Path(
    os.getenv(
        "TTS_DATA_DIR",
        str(BASE / "voices"),
    )
)

if (voice_dir / f"{voice}.onnx").exists():
    ok(f"Piper model: {voice}")
else:
    fail(f"brak modelu Piper {voice}")

try:
    import openwakeword

    found = None

    if hasattr(openwakeword, "MODELS"):
        entry = openwakeword.MODELS.get("hey_jarvis", {})
        candidate = entry.get("model_path")

        if candidate and Path(candidate).exists():
            found = Path(candidate)

        if not found and candidate:
            onnx = Path(
                str(candidate).replace(".tflite", ".onnx")
            )
            if onnx.exists():
                found = onnx

    if not found and hasattr(openwakeword, "models"):
        entry = openwakeword.models.get("hey_jarvis", {})
        candidate = entry.get("model_path")

        if candidate and Path(candidate).exists():
            found = Path(candidate)

    if found:
        ok(f"wake-word model: {found.name}")
    else:
        fail(
            "brak hey_jarvis; uruchom "
            "python ~/jarvis/tools/prepare_wakeword.py"
        )

except Exception as exc:
    fail(f"openWakeWord import: {exc}")

try:
    wpctl = subprocess.check_output(
        ["wpctl", "status"],
        text=True,
        timeout=5,
    )

    if "AP721113" in wpctl:
        ok("AP721113 widoczny w PipeWire")
    else:
        warn("AP721113 niewidoczny w PipeWire")

except Exception as exc:
    warn(f"nie udało się odczytać PipeWire: {exc}")

for service in (
    "jarvis-core.service",
    "jarvis-web.service",
):
    try:
        result = subprocess.run(
            [
                "systemctl",
                "--user",
                "is-enabled",
                service,
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )

        if result.stdout.strip() == "enabled":
            ok(f"{service} enabled")
        else:
            warn(f"{service} nie jest enabled")

    except Exception as exc:
        warn(f"{service}: {exc}")

try:
    from skills.system_health import raid_status, wifi_status

    wifi = wifi_status()

    if wifi["connected"]:
        ok(
            "Wi-Fi: "
            f"{wifi['band'] or '?'} "
            f"RX={wifi['rx_mbps']} "
            f"TX={wifi['tx_mbps']}"
        )
    else:
        warn("Wi-Fi niepołączone")

    raid = raid_status()

    if raid["present"]:
        if raid["healthy"]:
            ok(f"RAID {raid['name']}: {raid['state']}")
        elif raid["progress"] is not None:
            warn(
                f"RAID {raid['name']} recovery: "
                f"{raid['progress']}%"
            )
        else:
            warn(
                f"RAID {raid['name']} degraded: "
                f"{raid['state']}"
            )

except Exception as exc:
    warn(f"health check: {exc}")

print()
print(
    f"SELFTEST: {len(errors)} błędów, "
    f"{len(warnings)} ostrzeżeń"
)

raise SystemExit(1 if errors else 0)
