import os
import subprocess
import time
from collections import deque
from pathlib import Path

import numpy as np
import openwakeword
from dotenv import load_dotenv
from openwakeword.model import Model

load_dotenv(Path.home() / "jarvis" / ".env")

MIC_TARGET = os.getenv(
    "MIC_TARGET",
    "bluez_input.41:42:A0:17:EF:EA",
)

WAKE_THRESHOLD = float(os.getenv("WAKE_THRESHOLD", "0.50"))
WAKE_VAD_THRESHOLD = float(os.getenv("WAKE_VAD_THRESHOLD", "0.50"))
WAKE_DEBUG = os.getenv("WAKE_DEBUG", "0") == "1"
WAKE_SPEEX = os.getenv("WAKE_SPEEX", "1") == "1"
SCORE_WINDOW = max(1, int(os.getenv("WAKE_SCORE_WINDOW", "3")))
REQUIRED_HITS = max(1, int(os.getenv("WAKE_REQUIRED_HITS", "2")))
TICK_SECONDS = float(os.getenv("WAKE_TICK_SECONDS", "1.0"))

SAMPLE_RATE = 16000
CHANNELS = 1
FRAME_MS = 80
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000
FRAME_BYTES = FRAME_SAMPLES * 2


def _version():
    try:
        from importlib.metadata import version
        return version("openwakeword")
    except Exception:
        return "unknown"


def _model_info():
    """
    openWakeWord 0.5/0.6: MODELS + wakeword_models=
    openWakeWord 0.4:     models + wakeword_model_paths=
    Obsługujemy oba warianty, bo na Linux/Python 3.13 resolver
    może dobrać starszą wersję na części platform.
    """
    if hasattr(openwakeword, "MODELS"):
        entry = openwakeword.MODELS.get("hey_jarvis", {})
        path = entry.get("model_path")

        if path:
            path = Path(path)

            if path.exists():
                return "new", path

            onnx_path = Path(str(path).replace(".tflite", ".onnx"))

            if onnx_path.exists():
                return "new-onnx", onnx_path

    if hasattr(openwakeword, "models"):
        entry = openwakeword.models.get("hey_jarvis", {})
        path = entry.get("model_path")

        if path and Path(path).exists():
            return "legacy", Path(path)

    raise RuntimeError(
        "Nie znalazłem lokalnego modelu hey_jarvis w openWakeWord. "
        "Uruchom ~/jarvis/tools/prepare_wakeword.py."
    )


def _build_model():
    api, model_path = _model_info()

    common = {
        "enable_speex_noise_suppression": WAKE_SPEEX,
        "vad_threshold": WAKE_VAD_THRESHOLD,
    }

    def create(speex):
        common["enable_speex_noise_suppression"] = speex

        if api == "legacy":
            return Model(
                wakeword_model_paths=[str(model_path)],
                **common,
            )

        framework = (
            "onnx"
            if model_path.suffix.lower() == ".onnx"
            else "tflite"
        )

        return Model(
            wakeword_models=[str(model_path)],
            inference_framework=framework,
            **common,
        )

    try:
        model = create(WAKE_SPEEX)
        speex_active = WAKE_SPEEX
    except (ImportError, ModuleNotFoundError) as exc:
        if not WAKE_SPEEX:
            raise

        print(
            "⚠️ Speex niedostępny, wake-word działa bez niego: "
            f"{exc}",
            flush=True,
        )

        model = create(False)
        speex_active = False

    return model, api, model_path, speex_active


def _read_exact(stream, size):
    data = bytearray()

    while len(data) < size:
        chunk = stream.read(size - len(data))

        if not chunk:
            break

        data.extend(chunk)

    return bytes(data)


print(
    f"🔔 Ładowanie lokalnego wake-word "
    f"(openWakeWord {_version()})...",
    flush=True,
)

wake_model, wake_api, wake_model_path, wake_speex_active = _build_model()

print(
    "🔔 Lokalny wake-word gotowy "
    f"(api={wake_api}, "
    f"model={wake_model_path.name}, "
    f"threshold={WAKE_THRESHOLD:.2f}, "
    f"vad={WAKE_VAD_THRESHOLD:.2f}, "
    f"speex={'on' if wake_speex_active else 'off'}).",
    flush=True,
)


def _jarvis_score(predictions):
    best_name = None
    best_score = 0.0

    for name, score in predictions.items():
        if "jarvis" not in name.lower():
            continue

        try:
            score = float(score)
        except Exception:
            continue

        if score > best_score:
            best_name = name
            best_score = score

    return best_name, best_score


def wait_for_jarvis(
    tick_callback=None,
    *,
    timeout=None,
    stop_event=None,
    threshold=None,
    required_hits=None,
    announce=True,
):
    """
    Zwraca:
      "wake" - wykryto wake-word,
      "tick" - callback zgłosił zdarzenie,
      None   - timeout, stop_event albo capture zakończony/błąd.

    Parametry opcjonalne pozwalają użyć tego samego detektora
    do barge-in podczas wypowiedzi JARVIS-a.

    Audio nie opuszcza RPi.
    """
    process = subprocess.Popen(
        [
            "pw-record",
            "--target",
            MIC_TARGET,
            "--format",
            "s16",
            "--rate",
            str(SAMPLE_RATE),
            "--channels",
            str(CHANNELS),
            "-",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )

    effective_threshold = (
        WAKE_THRESHOLD
        if threshold is None
        else float(threshold)
    )
    effective_required_hits = max(
        1,
        REQUIRED_HITS
        if required_hits is None
        else int(required_hits),
    )

    scores = deque(maxlen=SCORE_WINDOW)
    hits = deque(maxlen=SCORE_WINDOW)

    if announce:
        print(
            "🌙 Czekam lokalnie na „Jarvis”…",
            flush=True,
        )

    started_at = time.monotonic()
    last_tick = started_at

    try:
        if process.stdout is None:
            return None

        while True:
            now = time.monotonic()

            if (
                stop_event is not None
                and stop_event.is_set()
            ):
                return None

            if (
                timeout is not None
                and now - started_at >= float(timeout)
            ):
                return None

            if (
                tick_callback is not None
                and now - last_tick >= TICK_SECONDS
            ):
                last_tick = now

                try:
                    if tick_callback():
                        return "tick"
                except Exception as exc:
                    print(
                        f"[WAKE TICK ERROR] {exc}",
                        flush=True,
                    )

            raw = _read_exact(
                process.stdout,
                FRAME_BYTES,
            )

            if len(raw) != FRAME_BYTES:
                err = ""

                if process.stderr:
                    try:
                        err = (
                            process.stderr.read()
                            .decode(errors="ignore")
                        )
                    except Exception:
                        pass

                if err.strip():
                    print(
                        f"[WAKE AUDIO ERROR] "
                        f"{err.strip()}",
                        flush=True,
                    )

                return None

            audio = np.frombuffer(
                raw,
                dtype=np.int16,
            )

            predictions = wake_model.predict(
                audio
            )

            model_name, score = _jarvis_score(
                predictions
            )

            scores.append(score)

            hits.append(
                1
                if score >= effective_threshold
                else 0
            )

            if (
                WAKE_DEBUG
                and score >= 0.03
            ):
                average = (
                    sum(scores)
                    / len(scores)
                )

                print(
                    f"🔎 wake={score:.3f} "
                    f"avg={average:.3f} "
                    f"hits={sum(hits)}/{len(hits)} "
                    f"model={model_name}",
                    flush=True,
                )

            if (
                model_name
                and len(hits) >= effective_required_hits
                and sum(hits) >= effective_required_hits
            ):
                average = (
                    sum(scores)
                    / len(scores)
                )

                if (
                    average
                    < effective_threshold * 0.65
                ):
                    continue

                print(
                    f"🔔 JARVIS wykryty "
                    f"(peak={score:.2f}, "
                    f"avg={average:.2f})",
                    flush=True,
                )

                try:
                    wake_model.reset()
                except Exception:
                    pass

                return "wake"

    finally:
        try:
            process.terminate()
            process.wait(timeout=1.0)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass
