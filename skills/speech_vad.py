import math
import os
import subprocess
import time
import wave
from array import array
from collections import deque
from pathlib import Path

import webrtcvad
from dotenv import load_dotenv

load_dotenv(Path.home() / "jarvis" / ".env")

MIC_TARGET = os.getenv(
    "MIC_TARGET",
    "bluez_input.41:42:A0:17:EF:EA",
)

SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2
FRAME_MS = 30
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000
FRAME_BYTES = FRAME_SAMPLES * SAMPLE_WIDTH

VAD_MODE = int(os.getenv("WEBRTC_VAD_MODE", "3"))
END_SILENCE_SECONDS = float(os.getenv("WEBRTC_END_SILENCE", "0.75"))
MAX_SPEECH_SECONDS = float(os.getenv("WEBRTC_MAX_SPEECH", "45"))
WAIT_SECONDS = float(os.getenv("WEBRTC_WAIT_SECONDS", "12"))
MIN_RMS = float(os.getenv("WEBRTC_MIN_RMS", "140"))
START_WINDOW = int(os.getenv("WEBRTC_START_WINDOW", "10"))
START_REQUIRED = int(os.getenv("WEBRTC_START_REQUIRED", "6"))
MIN_SPEECH_MS = int(os.getenv("WEBRTC_MIN_SPEECH_MS", "330"))
CALIBRATION_SECONDS = float(
    os.getenv("WEBRTC_CALIBRATION_SECONDS", "0.30")
)
NOISE_MULTIPLIER = float(
    os.getenv("WEBRTC_NOISE_MULTIPLIER", "1.75")
)
PREROLL_SECONDS = 0.45

_cached_noise_floor = None
_cached_threshold = None


def rms_level(data: bytes) -> float:
    if not data:
        return 0.0

    samples = array("h")
    samples.frombytes(data)

    if not samples:
        return 0.0

    total = sum(sample * sample for sample in samples)
    return math.sqrt(total / len(samples))


def median(values):
    if not values:
        return 0.0

    values = sorted(values)
    middle = len(values) // 2

    if len(values) % 2:
        return values[middle]

    return (values[middle - 1] + values[middle]) / 2.0


def read_exact(pipe, size):
    data = bytearray()

    while len(data) < size:
        chunk = pipe.read(size - len(data))
        if not chunk:
            break
        data.extend(chunk)

    return bytes(data)


def save_wav(filename, chunks):
    with wave.open(filename, "wb") as wav:
        wav.setnchannels(CHANNELS)
        wav.setsampwidth(SAMPLE_WIDTH)
        wav.setframerate(SAMPLE_RATE)

        for chunk in chunks:
            wav.writeframes(chunk)


def reset_noise_floor():
    global _cached_noise_floor, _cached_threshold
    _cached_noise_floor = None
    _cached_threshold = None


def _capture_process():
    return subprocess.Popen(
        [
            "pw-record",
            "--target", MIC_TARGET,
            "--format", "s16",
            "--rate", str(SAMPLE_RATE),
            "--channels", str(CHANNELS),
            "-",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )


def _calibrate(process, preroll):
    global _cached_noise_floor, _cached_threshold

    if _cached_threshold is not None:
        return True

    if process.stdout is None:
        return False

    count = max(
        1,
        int(CALIBRATION_SECONDS / (FRAME_MS / 1000)),
    )
    levels = []

    print("🎤 Krótka kalibracja tła...", flush=True)

    for _ in range(count):
        data = read_exact(process.stdout, FRAME_BYTES)

        if len(data) != FRAME_BYTES:
            return False

        levels.append(rms_level(data))
        preroll.append(data)

    _cached_noise_floor = median(levels)
    _cached_threshold = max(
        MIN_RMS,
        _cached_noise_floor * NOISE_MULTIPLIER,
    )

    print(
        f"🔧 VAD tło={_cached_noise_floor:.0f}, "
        f"próg={_cached_threshold:.0f}, "
        f"mode={VAD_MODE}",
        flush=True,
    )

    return True


def record_with_speech_vad(filename: str) -> bool:
    """
    WebRTC VAD + bramka RMS tylko przy rozpoczęciu wypowiedzi.
    Wymaga kilku ramek mowy, więc pojedynczy trzask/stuknięcie
    nie powinno uruchamiać Whispera.
    """
    global _cached_noise_floor, _cached_threshold

    vad = webrtcvad.Vad(VAD_MODE)
    process = _capture_process()

    preroll_frames = max(
        1,
        int(PREROLL_SECONDS / (FRAME_MS / 1000)),
    )
    preroll = deque(maxlen=preroll_frames)
    start_history = deque(maxlen=START_WINDOW)

    recorded = []
    voiced_frames = 0
    speech_started = False
    silence_frames = 0
    silence_needed = max(
        1,
        int(END_SILENCE_SECONDS / (FRAME_MS / 1000)),
    )
    waiting_started = time.monotonic()
    speech_started_at = None
    quiet_levels = deque(maxlen=80)

    try:
        if process.stdout is None:
            return False

        if not _calibrate(process, preroll):
            return False

        print("🎤 Nasłuchuję komendy...", flush=True)

        while True:
            data = read_exact(process.stdout, FRAME_BYTES)

            if len(data) != FRAME_BYTES:
                return False

            level = rms_level(data)

            try:
                is_voice = vad.is_speech(data, SAMPLE_RATE)
            except Exception:
                is_voice = False

            if not is_voice:
                quiet_levels.append(level)

            # Bardzo powolna adaptacja progu tylko w ciszy,
            # żeby nie "uczyć" VAD-u na głosie użytkownika.
            if (
                not speech_started
                and len(quiet_levels) >= 40
            ):
                recent_noise = median(list(quiet_levels))
                if _cached_noise_floor is None:
                    _cached_noise_floor = recent_noise
                else:
                    _cached_noise_floor = (
                        _cached_noise_floor * 0.92
                        + recent_noise * 0.08
                    )

                _cached_threshold = max(
                    MIN_RMS,
                    _cached_noise_floor * NOISE_MULTIPLIER,
                )

            voice_candidate = (
                is_voice
                and level >= float(_cached_threshold)
            )

            if not speech_started:
                preroll.append(data)
                start_history.append(1 if voice_candidate else 0)

                if (
                    len(start_history) == START_WINDOW
                    and sum(start_history) >= START_REQUIRED
                ):
                    speech_started = True
                    speech_started_at = time.monotonic()
                    recorded.extend(preroll)
                    preroll.clear()
                    voiced_frames += sum(start_history)
                    silence_frames = 0

                    print(
                        "🗣️ Wykryto stabilny początek mowy",
                        flush=True,
                    )
                    continue

                if time.monotonic() - waiting_started >= WAIT_SECONDS:
                    return False

                continue

            recorded.append(data)

            if is_voice:
                voiced_frames += 1
                silence_frames = 0
            else:
                silence_frames += 1

            if silence_frames >= silence_needed:
                break

            if (
                speech_started_at is not None
                and time.monotonic() - speech_started_at
                >= MAX_SPEECH_SECONDS
            ):
                break

    finally:
        try:
            process.terminate()
            process.wait(timeout=1.0)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    speech_ms = voiced_frames * FRAME_MS

    if speech_ms < MIN_SPEECH_MS:
        print(
            f"🛡️ Odrzucono szum/trzask: "
            f"{speech_ms} ms mowy.",
            flush=True,
        )
        return False

    if not recorded:
        return False

    save_wav(filename, recorded)

    print(
        f"✓ Nagranie {len(recorded) * FRAME_MS / 1000:.1f}s, "
        f"mowa={speech_ms}ms",
        flush=True,
    )

    return True
