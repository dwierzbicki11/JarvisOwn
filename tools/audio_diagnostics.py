import math
import os
import subprocess
import time
from array import array
from pathlib import Path

from dotenv import load_dotenv

BASE = Path.home() / "jarvis"
load_dotenv(BASE / ".env")

MIC = os.getenv(
    "MIC_TARGET",
    "bluez_input.41:42:A0:17:EF:EA",
)

RATE = 16000
SECONDS = 8
CHUNK_SAMPLES = 1600
CHUNK_BYTES = CHUNK_SAMPLES * 2


def rms(data):
    samples = array("h")
    samples.frombytes(data)

    if not samples:
        return 0.0

    total = sum(
        sample * sample
        for sample in samples
    )

    return math.sqrt(
        total / len(samples)
    )


print("=== JARVIS AUDIO DIAGNOSTICS ===")
print(f"MIC_TARGET: {MIC}")

try:
    status = subprocess.check_output(
        ["wpctl", "status"],
        text=True,
        timeout=5,
    )
    print(status)
except Exception as exc:
    print(f"wpctl error: {exc}")

process = subprocess.Popen(
    [
        "pw-record",
        "--target",
        MIC,
        "--format",
        "s16",
        "--rate",
        str(RATE),
        "--channels",
        "1",
        "-",
    ],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    bufsize=0,
)

print(
    "Mów normalnie, klaśnij i zrób typowy hałas w pokoju. "
    f"Pomiar potrwa {SECONDS}s."
)

levels = []
started = time.monotonic()

try:
    while time.monotonic() - started < SECONDS:
        data = process.stdout.read(CHUNK_BYTES)

        if len(data) != CHUNK_BYTES:
            break

        level = rms(data)
        levels.append(level)

        bars = min(
            60,
            int(level / 120),
        )

        print(
            f"{level:7.0f} | "
            + "█" * bars,
            flush=True,
        )

finally:
    try:
        process.terminate()
        process.wait(timeout=1)
    except Exception:
        process.kill()

if not levels:
    print("Brak próbek audio.")
    raise SystemExit(1)

ordered = sorted(levels)

def percentile(p):
    index = int(
        max(
            0,
            min(
                len(ordered) - 1,
                round(
                    (len(ordered) - 1)
                    * p
                ),
            ),
        )
    )
    return ordered[index]


print()
print("=== PODSUMOWANIE ===")
print(f"minimum: {min(levels):.0f}")
print(f"p50:     {percentile(0.50):.0f}")
print(f"p90:     {percentile(0.90):.0f}")
print(f"p95:     {percentile(0.95):.0f}")
print(f"maximum: {max(levels):.0f}")
print()
print(
    "Jeżeli zwykłe tło ma RMS dużo niższy niż głos, "
    "WEBRTC_MIN_RMS można dobrać między nimi."
)
