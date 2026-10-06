import json
import os
import re
import subprocess
import tempfile
import threading
import time
import wave
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import psutil
from dotenv import load_dotenv
from groq import Groq
from piper import PiperVoice

from skills.background_events import BackgroundEvents
from skills.conversation_history import (
    append_turn,
    clear_history,
    format_recent_history,
    last_turn,
    recent_messages,
    recent_turns,
)
from skills.audio_manager import (
    playback_target,
    prepare_audio,
    wait_after_playback,
)
from skills.krakow_transport import next_departures, transit_alerts
from skills.local_wakeword import wait_for_jarvis
from skills.memory_store import (
    forget_latest,
    memory_context,
    recent_memories,
    remember,
)
from skills.pk_calendar import (
    answer_calendar_question,
    get_first_class,
    get_next_class,
    get_schedule,
)
from skills.reminders import (
    add_reminder,
    cancel_latest,
    format_pending,
    parse_reminder_command,
)
from skills.route_planner import (
    CLASS_BUFFER_MINUTES,
    HOME_STOP,
    PK_STOP,
    PK_WALK_MINUTES,
    find_journey,
    format_journey,
)
from skills.speech_vad import record_with_speech_vad
from skills.speech_formatter import speechify_math
from skills.speaker_verify import profile_status as speaker_profile_status, verify_wav
from skills.study import detect_study_subject, study_prompt
from skills.study_materials import (
    find_material,
    list_materials,
    material_for_prompt,
    search_materials,
)
from skills.study_rag import (
    build_context,
    index_status as study_index_status,
    rebuild_index as rebuild_study_index,
)
from skills.system_health import short_health_text
from skills.weather import get_weather
from skills.voice_router import classify_voice_intent


BASE_DIR = Path.home() / "jarvis"
load_dotenv(BASE_DIR / ".env")

TIMEZONE = ZoneInfo("Europe/Warsaw")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
STT_MODEL = os.getenv("STT_MODEL", "whisper-large-v3")
CHAT_MODEL = os.getenv("CHAT_MODEL", "openai/gpt-oss-20b")

TTS_VOICE = os.getenv("TTS_VOICE", "pl_PL-mc_speech-medium")
TTS_DATA_DIR = Path(
    os.getenv(
        "TTS_DATA_DIR",
        str(BASE_DIR / "voices"),
    )
)
TTS_MODEL_PATH = TTS_DATA_DIR / f"{TTS_VOICE}.onnx"

SESSION_SECONDS = float(os.getenv("JARVIS_SESSION_SECONDS", "30"))
AUTO_SLEEP_MINUTES = float(os.getenv("AUTO_SLEEP_MINUTES", "0"))
AUDIO_CLEANUP = os.getenv("AUDIO_CLEANUP", "1") == "1"
CONVERSATION_HISTORY_MESSAGES = max(
    4,
    int(
        os.getenv(
            "CONVERSATION_HISTORY_MESSAGES",
            "24",
        )
    ),
)
SINGLE_UTTERANCE_WAKE = os.getenv(
    "SINGLE_UTTERANCE_WAKE",
    "1",
) == "1"
WAKE_COMMAND_GRACE_SECONDS = float(
    os.getenv(
        "WAKE_COMMAND_GRACE_SECONDS",
        "1.6",
    )
)
ACTIVE_LISTEN_TIMEOUT = float(
    os.getenv(
        "ACTIVE_LISTEN_TIMEOUT",
        "8",
    )
)
BARGE_IN_ENABLED = os.getenv(
    "BARGE_IN_ENABLED",
    "1",
) == "1"
BARGE_IN_WAKE_THRESHOLD = float(
    os.getenv(
        "BARGE_IN_WAKE_THRESHOLD",
        "0.65",
    )
)
BARGE_IN_REQUIRED_HITS = max(
    1,
    int(
        os.getenv(
            "BARGE_IN_REQUIRED_HITS",
            "2",
        )
    ),
)
BARGE_IN_START_DELAY = float(
    os.getenv(
        "BARGE_IN_START_DELAY",
        "0.35",
    )
)

GUI_STATE_FILE = BASE_DIR / "runtime" / "state.json"
GUI_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

if not GROQ_API_KEY:
    raise RuntimeError("Brak GROQ_API_KEY w ~/jarvis/.env")

if not TTS_MODEL_PATH.exists():
    raise RuntimeError(f"Brak modelu Piper: {TTS_MODEL_PATH}")

client = Groq(api_key=GROQ_API_KEY)

print("🔊 Ładowanie Piper...", flush=True)
tts_voice = PiperVoice.load(str(TTS_MODEL_PATH))
print("🔊 Piper gotowy.", flush=True)

english_mode = False
study_mode = None
exam_mode = False

background_events = BackgroundEvents()

_gui_state = {
    "state": "starting",
    "last_user": "",
    "last_answer": "",
    "study_mode": None,
    "exam_mode": False,
    "last_latency": {},
    "speaker": {},
    "updated": time.time(),
}


def set_gui_state(
    state=None,
    last_user=None,
    last_answer=None,
    latency=None,
    speaker=None,
):
    _gui_state["study_mode"] = study_mode
    _gui_state["exam_mode"] = exam_mode

    if state is not None:
        _gui_state["state"] = state

    if last_user is not None:
        _gui_state["last_user"] = last_user

    if last_answer is not None:
        _gui_state["last_answer"] = last_answer

    if latency is not None:
        _gui_state["last_latency"] = latency

    if speaker is not None:
        _gui_state["speaker"] = speaker

    _gui_state["updated"] = time.time()

    tmp = GUI_STATE_FILE.with_suffix(".tmp")

    try:
        tmp.write_text(
            json.dumps(_gui_state, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(GUI_STATE_FILE)
    except Exception as exc:
        print(f"[GUI STATE ERROR] {exc}", flush=True)


def perf_start(name):
    print(f"⏱️ START {name}", flush=True)
    return time.monotonic()


def perf_end(name, started):
    elapsed = time.monotonic() - started

    print(
        f"⏱️ {name}: {elapsed:.2f}s",
        flush=True,
    )

    latency = dict(_gui_state.get("last_latency") or {})
    latency[name] = round(elapsed, 2)
    set_gui_state(latency=latency)

    return elapsed


def normalize_text(text):
    return (
        re.sub(r"\s+", " ", text.lower().strip())
        .rstrip(".!?")
    )


def _number_words_0_59(number):
    units = {
        0: "zero",
        1: "jeden",
        2: "dwa",
        3: "trzy",
        4: "cztery",
        5: "pięć",
        6: "sześć",
        7: "siedem",
        8: "osiem",
        9: "dziewięć",
        10: "dziesięć",
        11: "jedenaście",
        12: "dwanaście",
        13: "trzynaście",
        14: "czternaście",
        15: "piętnaście",
        16: "szesnaście",
        17: "siedemnaście",
        18: "osiemnaście",
        19: "dziewiętnaście",
    }

    tens = {
        20: "dwadzieścia",
        30: "trzydzieści",
        40: "czterdzieści",
        50: "pięćdziesiąt",
    }

    if number <= 19:
        return units[number]

    base = number // 10 * 10
    rest = number % 10

    if not rest:
        return tens[base]

    return tens[base] + " " + units[rest]


def _spoken_clock(hour, minute):
    hours = {
        0: "północy",
        1: "pierwszej",
        2: "drugiej",
        3: "trzeciej",
        4: "czwartej",
        5: "piątej",
        6: "szóstej",
        7: "siódmej",
        8: "ósmej",
        9: "dziewiątej",
        10: "dziesiątej",
        11: "jedenastej",
        12: "dwunastej",
        13: "trzynastej",
        14: "czternastej",
        15: "piętnastej",
        16: "szesnastej",
        17: "siedemnastej",
        18: "osiemnastej",
        19: "dziewiętnastej",
        20: "dwudziestej",
        21: "dwudziestej pierwszej",
        22: "dwudziestej drugiej",
        23: "dwudziestej trzeciej",
    }

    if minute == 0:
        return hours[hour]

    minute_text = (
        "zero " + _number_words_0_59(minute)
        if minute < 10
        else _number_words_0_59(minute)
    )

    return f"{hours[hour]} {minute_text}"


def normalize_for_speech(text: str) -> str:
    replacements = {
        "AKF / PK": "A ka ef, Politechnika Krakowska",
        "AKF/PK": "A ka ef, Politechnika Krakowska",
        "P+R": "Parkuj i Jedź",
        "P & R": "Parkuj i Jedź",
        "P&R": "Parkuj i Jedź",
        "GTFS": "gie te ef es",
        "CPU": "ce pe u",
        "RAM": "ram",
        "Pi-hole": "Paj hol",
        "Pi Hole": "Paj hol",
        "Docker": "Doker",
        "Whisper": "Łisper",
        "Piper": "Pajper",
        "Raspberry Pi": "Raspberry Paj",
    }

    spoken = speechify_math(
        text,
        client=client,
        model=CHAT_MODEL,
    )

    for source in sorted(replacements, key=len, reverse=True):
        spoken = spoken.replace(
            source,
            replacements[source],
        )

    def replace_clock(match):
        hour = int(match.group(1))
        minute = int(match.group(2))

        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return _spoken_clock(hour, minute)

        return match.group(0)

    spoken = re.sub(
        r"\b([01]?\d|2[0-3]):([0-5]\d)\b",
        replace_clock,
        spoken,
    )

    letter_names = {
        "A": "a",
        "B": "be",
        "C": "ce",
        "D": "de",
        "E": "e",
        "F": "ef",
    }

    digit_names = {
        "0": "zero",
        "1": "jeden",
        "2": "dwa",
        "3": "trzy",
        "4": "cztery",
        "5": "pięć",
        "6": "sześć",
        "7": "siedem",
        "8": "osiem",
        "9": "dziewięć",
    }

    def room_replacer(match):
        letter = letter_names.get(
            match.group(1),
            match.group(1),
        )
        number = " ".join(
            digit_names[d]
            for d in match.group(2)
        )

        return f"{letter} {number}"

    spoken = re.sub(
        r"\b([A-F])(\d{2})\b",
        room_replacer,
        spoken,
    )

    spoken = spoken.replace("—", ",")
    return re.sub(r"\s+", " ", spoken).strip()


def _barge_in_watch(
    stop_event,
    wake_event,
):
    """
    Nasłuchuje lokalnego wake-word podczas odtwarzania TTS.

    To nie wysyła audio do chmury. Wyższy próg niż w standby
    ogranicza przypadkowe przerwania od dźwięków w pokoju.
    """
    if BARGE_IN_START_DELAY > 0:
        stop_event.wait(
            BARGE_IN_START_DELAY
        )

    if stop_event.is_set():
        return

    try:
        reason = wait_for_jarvis(
            timeout=None,
            stop_event=stop_event,
            threshold=BARGE_IN_WAKE_THRESHOLD,
            required_hits=BARGE_IN_REQUIRED_HITS,
            announce=False,
        )

        if reason == "wake":
            wake_event.set()

    except Exception as exc:
        print(
            f"[BARGE-IN ERROR] {exc}",
            flush=True,
        )


def speak(text: str):
    print(f"\nJARVIS: {text}\n", flush=True)
    set_gui_state(
        "speaking",
        last_answer=text,
    )

    timer = perf_start("Piper+playback")
    wav_path = None

    try:
        with tempfile.NamedTemporaryFile(
            suffix=".wav",
            delete=False,
        ) as tmp:
            wav_path = tmp.name

        spoken_text = normalize_for_speech(text)

        with wave.open(wav_path, "wb") as wav_file:
            tts_voice.synthesize_wav(
                spoken_text,
                wav_file,
            )

        # Krótka przerwa na zwolnienie profilu BT po nagrywaniu.
        time.sleep(0.20)

        sink_id = playback_target()

        if sink_id:
            subprocess.run(
                ["wpctl", "set-default", sink_id],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )

            subprocess.run(
                ["wpctl", "set-mute", sink_id, "0"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )

            command = [
                "pw-play",
                "--target",
                sink_id,
                wav_path,
            ]
        else:
            command = [
                "pw-play",
                wav_path,
            ]

        stop_event = threading.Event()
        wake_event = threading.Event()
        watcher = None

        # Gdy sam TTS wypowiada słowo "Jarvis", nie uruchamiaj
        # detektora barge-in, bo echo mogłoby przerwać własną odpowiedź.
        can_barge_in = (
            BARGE_IN_ENABLED
            and "jarvis" not in spoken_text.lower()
        )

        if can_barge_in:
            watcher = threading.Thread(
                target=_barge_in_watch,
                args=(
                    stop_event,
                    wake_event,
                ),
                daemon=True,
                name="jarvis-barge-in",
            )
            watcher.start()

        playback = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )

        interrupted = False

        while playback.poll() is None:
            if wake_event.is_set():
                interrupted = True

                print(
                    "🛑 BARGE-IN: przerwano odpowiedź.",
                    flush=True,
                )

                try:
                    playback.terminate()
                    playback.wait(
                        timeout=0.7
                    )
                except Exception:
                    try:
                        playback.kill()
                    except Exception:
                        pass

                break

            time.sleep(0.05)

        stop_event.set()

        if watcher is not None:
            watcher.join(
                timeout=0.5
            )

        stderr = ""

        if playback.stderr is not None:
            try:
                stderr = playback.stderr.read()
            except Exception:
                stderr = ""

        if (
            playback.returncode not in (
                0,
                None,
                -15,
            )
            and not interrupted
        ):
            print(
                f"[PW-PLAY ERROR] "
                f"{stderr.strip()}",
                flush=True,
            )

        if interrupted:
            set_gui_state(
                "listening"
            )
        else:
            wait_after_playback()

    except Exception as exc:
        print(
            f"[TTS ERROR] {exc}",
            flush=True,
        )

    finally:
        if wav_path:
            try:
                os.remove(wav_path)
            except OSError:
                pass

        perf_end(
            "Piper+playback",
            timer,
        )


def clean_audio(source, destination):
    timer = perf_start("Audio cleanup")

    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-i",
                source,
                "-af",
                (
                    "highpass=f=100,"
                    "lowpass=f=7200,"
                    "afftdn=nf=-25,"
                    "acompressor=threshold=-24dB:ratio=4:attack=8:release=120,"
                    "loudnorm=I=-20:TP=-2:LRA=7"
                ),
                "-ar",
                "16000",
                "-ac",
                "1",
                destination,
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )

        if result.returncode != 0:
            print(
                f"[FFMPEG ERROR] "
                f"{result.stderr.strip()}",
                flush=True,
            )
            return False

        return True

    except subprocess.TimeoutExpired:
        print(
            "[FFMPEG ERROR] timeout",
            flush=True,
        )
        return False

    finally:
        perf_end(
            "Audio cleanup",
            timer,
        )


def transcribe_audio(filename):
    timer = perf_start("Whisper")

    try:
        with open(filename, "rb") as file:
            transcription = (
                client.audio.transcriptions.create(
                    file=(
                        Path(filename).name,
                        file.read(),
                    ),
                    model=STT_MODEL,
                    language="pl",
                    prompt=(
                        "Polski asystent JARVIS. "
                        "Nazwy: Jarvis, "
                        "Politechnika Krakowska, "
                        "AKF PK, "
                        "Garlica Duchowna Kapliczka, "
                        "Krowodrza Górka, "
                        "Raspberry Pi, Docker, Pi-hole."
                    ),
                )
            )

        text = transcription.text.strip()

        # Odrzuć bardzo częste śmieci/hallucynacje na ciszy.
        garbage = {
            "dziękuję",
            "dziękuję za uwagę",
            "napisy stworzone przez społeczność amara.org",
            "subtitles by the amara.org community",
        }

        if normalize_text(text) in garbage:
            print(
                f"🛡️ Odrzucono STT garbage: {text}",
                flush=True,
            )
            return ""

        return text

    except Exception as exc:
        print(
            f"[WHISPER ERROR] {exc}",
            flush=True,
        )
        return ""

    finally:
        perf_end(
            "Whisper",
            timer,
        )


def listen_command(wait_seconds=None):
    raw_path = None
    cleaned_path = None

    try:
        with tempfile.NamedTemporaryFile(
            suffix=".wav",
            delete=False,
        ) as raw:
            raw_path = raw.name

        with tempfile.NamedTemporaryFile(
            suffix=".wav",
            delete=False,
        ) as clean:
            cleaned_path = clean.name

        set_gui_state("listening")

        timer = perf_start("VAD")

        recorded = record_with_speech_vad(
            raw_path,
            wait_seconds=wait_seconds,
        )

        perf_end(
            "VAD",
            timer,
        )

        if not recorded:
            return None

        speaker = verify_wav(
            raw_path
        )

        set_gui_state(
            speaker={
                "enabled": bool(
                    speaker.get(
                        "enabled",
                        False,
                    )
                ),
                "enrolled": bool(
                    speaker.get(
                        "enrolled",
                        False,
                    )
                ),
                "accepted": bool(
                    speaker.get(
                        "accepted",
                        True,
                    )
                ),
                "similarity": speaker.get(
                    "similarity"
                ),
                "threshold": speaker.get(
                    "threshold"
                ),
                "reason": speaker.get(
                    "reason"
                ),
            }
        )

        if (
            speaker.get("enabled")
            and speaker.get("enrolled")
        ):
            similarity = speaker.get(
                "similarity"
            )

            if similarity is not None:
                print(
                    "🗣️ Speaker match="
                    f"{similarity:.3f} "
                    f"threshold="
                    f"{speaker.get('threshold', 0):.3f}",
                    flush=True,
                )

        if not speaker.get(
            "accepted",
            True,
        ):
            print(
                "🛡️ Odrzucono komendę: "
                "głos nie pasuje do profilu użytkownika.",
                flush=True,
            )
            return None

        if (
            speaker.get("reason")
            == "profile_missing"
        ):
            print(
                "⚠️ Speaker verification jest włączone, "
                "ale brak profilu. Komenda została przepuszczona.",
                flush=True,
            )

        if (
            speaker.get("reason")
            == "verification_error"
        ):
            print(
                "[SPEAKER VERIFY ERROR] "
                + str(
                    speaker.get(
                        "error",
                        "unknown",
                    )
                ),
                flush=True,
            )

        stt_file = raw_path

        if AUDIO_CLEANUP:
            if clean_audio(
                raw_path,
                cleaned_path,
            ):
                stt_file = cleaned_path

        text = transcribe_audio(
            stt_file
        )

        if not text:
            return None

        print(
            f"USŁYSZANO: {text}",
            flush=True,
        )

        set_gui_state(
            last_user=text,
        )

        return text

    finally:
        for path in (
            raw_path,
            cleaned_path,
        ):
            if path:
                try:
                    os.remove(path)
                except OSError:
                    pass


def docker_status():
    try:
        output = subprocess.check_output(
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
            for line in output.splitlines()
            if line.strip()
        ]

        if not names:
            return (
                "Nie ma uruchomionych "
                "kontenerów Dockera."
            )

        return (
            f"Działa {len(names)} "
            f"kontenerów Dockera: "
            + ", ".join(names)
            + "."
        )

    except Exception:
        return (
            "Nie mogę teraz odczytać Dockera."
        )


def pihole_status():
    result = subprocess.run(
        [
            "systemctl",
            "is-active",
            "pihole-FTL",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.stdout.strip() == "active":
        return "Pi-hole działa."

    return "Pi-hole nie jest aktywny."


def system_status():
    cpu = round(
        psutil.cpu_percent(
            interval=0.1
        )
    )

    ram = round(
        psutil.virtual_memory().percent
    )

    disk = round(
        psutil.disk_usage("/").percent
    )

    temp = None

    try:
        temp = round(
            int(
                Path(
                    "/sys/class/thermal/"
                    "thermal_zone0/temp"
                ).read_text().strip()
            )
            / 1000
        )
    except Exception:
        pass

    result = (
        f"CPU {cpu} procent. "
        f"RAM {ram} procent. "
        f"Dysk {disk} procent."
    )

    if temp is not None:
        result += (
            f" Temperatura procesora "
            f"{temp} stopni."
        )

    return result


def trip_to_first_class(
    day_offset=1,
):
    first_class = get_first_class(
        day_offset
    )

    if not first_class:
        if day_offset == 1:
            return (
                "Nie masz jutro zajęć "
                "w kalendarzu."
            )

        return (
            "Nie znalazłem zajęć "
            "w tym dniu."
        )

    class_time = first_class["start"]

    latest_arrival = (
        class_time
        - timedelta(
            minutes=(
                PK_WALK_MINUTES
                + CLASS_BUFFER_MINUTES
            )
        )
    )

    timer = perf_start(
        "GTFS route"
    )

    journey = find_journey(
        target_date=class_time.date(),
        origin_name=HOME_STOP,
        destination_name=PK_STOP,
        latest_arrival=latest_arrival,
    )

    perf_end(
        "GTFS route",
        timer,
    )

    answer = format_journey(
        journey,
        class_time=class_time,
    )

    if "error" not in journey:
        answer += (
            " To plan na podstawie "
            "rozkładu GTFS."
        )

    return answer


def today_brief():
    parts = []

    try:
        parts.append(
            get_schedule(
                day_offset=0
            )
        )
    except Exception as exc:
        print(
            f"[BRIEF CALENDAR ERROR] "
            f"{exc}",
            flush=True,
        )

    try:
        parts.append(
            get_weather(
                tomorrow=False
            )
        )
    except Exception as exc:
        print(
            f"[BRIEF WEATHER ERROR] "
            f"{exc}",
            flush=True,
        )

    try:
        parts.append(
            transit_alerts(
                limit=2
            )
        )
    except Exception as exc:
        print(
            f"[BRIEF ALERT ERROR] "
            f"{exc}",
            flush=True,
        )

    return " ".join(
        part
        for part in parts
        if part
    )


def tomorrow_brief():
    parts = []

    try:
        parts.append(
            get_schedule(
                day_offset=1
            )
        )
    except Exception as exc:
        print(
            f"[BRIEF CALENDAR ERROR] "
            f"{exc}",
            flush=True,
        )

    try:
        parts.append(
            get_weather(
                tomorrow=True
            )
        )
    except Exception as exc:
        print(
            f"[BRIEF WEATHER ERROR] "
            f"{exc}",
            flush=True,
        )

    try:
        parts.append(
            trip_to_first_class(
                day_offset=1
            )
        )
    except Exception as exc:
        print(
            f"[BRIEF ROUTE ERROR] "
            f"{exc}",
            flush=True,
        )

    try:
        parts.append(
            transit_alerts(
                limit=2
            )
        )
    except Exception as exc:
        print(
            f"[BRIEF ALERT ERROR] "
            f"{exc}",
            flush=True,
        )

    return " ".join(
        part
        for part in parts
        if part
    )


SYSTEM_PROMPT = """
Jesteś JARVIS-em, prywatnym asystentem użytkownika.
Domyślnie odpowiadasz po polsku, naturalnie i zwięźle,
bo odpowiedzi są czytane głosowo.

Główne zadania:
- matematyka,
- programowanie,
- język angielski,
- nauka na studiach,
- codzienna organizacja.

Nie wymyślaj bieżącej pogody, transportu, planu zajęć,
przypomnień ani stanu serwera. Te dane obsługują lokalne moduły.
Jeśli pytanie o prywatne dane użytkownika mimo wszystko trafi do ciebie
bez wyników lokalnego modułu, nie mów "nie mam dostępu".
Powiedz krótko, że lokalny moduł nie zwrócił potrzebnych danych.
Jeśli użytkownik się uczy, pomagaj mu zrozumieć temat,
a nie tylko podawaj wynik.
"""


def llm_answer(text):
    timer = perf_start(
        "Groq chat"
    )

    subject = (
        study_mode
        or detect_study_subject(text)
    )

    system = SYSTEM_PROMPT

    if subject:
        system += (
            "\n\n"
            + study_prompt(subject)
        )

    if exam_mode:
        system += (
            "\n\nTryb egzaminu jest aktywny. "
            "Nie podawaj rozwiązania od razu. "
            "Zadawaj pytania, oceniaj odpowiedzi "
            "i dawaj tylko tyle wskazówek, ile potrzeba."
        )

    if english_mode:
        system += (
            "\n\nEnglish mode jest aktywny. "
            "Prowadź rozmowę po angielsku, "
            "chyba że użytkownik poprosi inaczej. "
            "Po wypowiedzi popraw najważniejsze błędy, "
            "ale nie przerywaj płynności rozmowy."
        )

    remembered = memory_context(
        limit=8
    )

    if remembered:
        system += (
            "\n\nJawnie zapisane informacje "
            "użytkownika, które możesz wykorzystać:\n"
            + remembered
        )

    history_messages = recent_messages(
        limit_messages=CONVERSATION_HISTORY_MESSAGES
    )

    messages = [
        {
            "role": "system",
            "content": system,
        },
        *history_messages,
        {
            "role": "user",
            "content": text,
        },
    ]

    try:
        completion = (
            client.chat.completions.create(
                model=CHAT_MODEL,
                messages=messages,
                temperature=0.30,
                max_tokens=650,
            )
        )

        answer = (
            completion
            .choices[0]
            .message
            .content
            .strip()
        )

        return answer

    except Exception as exc:
        print(
            f"[LLM ERROR] {exc}",
            flush=True,
        )

        return (
            "Nie mogę teraz połączyć się "
            "z modelem językowym. "
            "Spróbuj za chwilę."
        )

    finally:
        perf_end(
            "Groq chat",
            timer,
        )



def answer_from_study_rag(
    text,
    *,
    quiz=False,
):
    """
    Odpowiada na podstawie lokalnych materiałów użytkownika.

    Do modelu wysyłamy tylko najbardziej trafne fragmenty,
    a nie cały katalog materiałów.
    """
    try:
        context, sources = build_context(
            text,
            limit=6,
            max_chars=10000,
        )
    except Exception as exc:
        return (
            "Nie mogę teraz przeszukać materiałów. "
            f"{exc}"
        )

    if not context:
        return (
            "Nie znalazłem w twoich materiałach "
            "fragmentów pasujących do tego pytania."
        )

    if quiz:
        instruction = (
            "Przepytuj użytkownika WYŁĄCZNIE na podstawie "
            "poniższych fragmentów jego materiałów. "
            "Zadaj jedno konkretne pytanie i nie podawaj "
            "odpowiedzi, dopóki użytkownik sam nie odpowie."
        )
    else:
        instruction = (
            "Odpowiedz WYŁĄCZNIE na podstawie poniższych "
            "fragmentów materiałów użytkownika. "
            "Jeśli fragmenty nie wystarczają do odpowiedzi, "
            "powiedz to wprost zamiast uzupełniać wiedzą ogólną. "
            "Na końcu krótko podaj nazwy wykorzystanych źródeł."
        )

    source_text = ", ".join(
        sources
    )

    prompt = (
        f"{instruction}\n\n"
        f"Pytanie użytkownika:\n{text}\n\n"
        f"Materiały:\n{context}\n\n"
        f"Dostępne źródła: {source_text}"
    )

    return llm_answer(prompt)


def answer_from_study_material(text, quiz=False):
    lower = normalize_text(text)

    # Nazwa materiału po "z" lub "z pliku".
    match = re.search(
        r"(?:z pliku|z materiału|z materialu|z)\s+(.+)$",
        text,
        flags=re.IGNORECASE,
    )

    material = None

    if match:
        candidate = match.group(1).strip().strip('"')
        material = find_material(candidate)

    if material is None:
        results = search_materials(text, limit=1)

        if results:
            material = results[0]["path"]

    if material is None:
        return (
            "Nie znalazłem pasującego materiału w folderze "
            "~/jarvis/study_materials. "
            "Wrzuć tam PDF, TXT, Markdown albo plik z kodem."
        )

    try:
        content = material_for_prompt(material)
    except Exception as exc:
        return f"Nie mogę odczytać materiału {material.name}: {exc}"

    mode_instruction = (
        "Przepytuj użytkownika z tego materiału. "
        "Zadawaj jedno pytanie na raz, nie podawaj odpowiedzi od razu."
        if quiz
        else
        "Wytłumacz materiał jasno, skupiając się na najważniejszych pojęciach "
        "i zaproponuj krótkie ćwiczenie."
    )

    prompt = (
        f"{mode_instruction}\n\n"
        f"Nazwa materiału: {material.name}\n\n"
        f"Treść materiału:\n{content}"
    )

    return llm_answer(prompt)

def _set_study_mode(
    mode,
):
    global study_mode
    global english_mode

    study_mode = mode

    if mode == "angielski":
        english_mode = True

    set_gui_state()

    if mode is None:
        return (
            "Wyłączam tryb nauki."
        )

    if mode == "matematyka":
        return (
            "Tryb nauki matematyki włączony. "
            "Będę prowadził rozwiązania krok po kroku."
        )

    if mode == "programowanie":
        return (
            "Tryb nauki programowania włączony. "
            "Skupimy się na rozumieniu kodu i debugowaniu."
        )

    if mode == "angielski":
        return (
            "English study mode enabled. "
            "Let's practice naturally."
        )

    return (
        f"Tryb nauki {mode} włączony."
    )


def process_memory_command(
    text,
    lower,
):
    remember_match = re.search(
        r"(?:zapamiętaj|zapamietaj)(?:,)?\s+"
        r"(?:że|ze)\s+(.+)",
        text,
        flags=re.IGNORECASE,
    )

    if remember_match:
        item = (
            remember_match
            .group(1)
            .strip()
            .rstrip(".")
        )

        if remember(item):
            return (
                "Zapamiętałem."
            )

    if (
        "co pamiętasz" in lower
        or "co pamietasz" in lower
    ):
        rows = recent_memories(
            limit=8
        )

        if not rows:
            return (
                "Nie mam jeszcze zapisanych "
                "informacji."
            )

        rows.reverse()

        return (
            "Pamiętam: "
            + "; ".join(
                row["text"]
                for row in rows
            )
            + "."
        )

    if (
        "zapomnij ostatnią" in lower
        or "zapomnij ostatnia" in lower
        or "usuń ostatnią pamięć" in lower
        or "usun ostatnia pamiec" in lower
    ):
        removed = forget_latest()

        if not removed:
            return (
                "Nie mam czego usuwać."
            )

        return (
            "Usunąłem ostatnio zapisaną informację."
        )

    return None


def process_reminder_command(
    text,
    lower,
):
    parsed = parse_reminder_command(
        text
    )

    if parsed:
        due_at, reminder_text = parsed
        add_reminder(
            due_at,
            reminder_text,
        )

        return (
            "Ustawione. Przypomnę "
            f"{due_at.strftime('%d.%m o %H:%M')}: "
            f"{reminder_text}."
        )

    if (
        "jakie mam przypomnienia" in lower
        or "pokaż przypomnienia" in lower
        or "pokaz przypomnienia" in lower
    ):
        return format_pending(
            limit=5
        )

    if (
        "usuń ostatnie przypomnienie" in lower
        or "usun ostatnie przypomnienie" in lower
        or "anuluj ostatnie przypomnienie" in lower
    ):
        removed = cancel_latest()

        if not removed:
            return (
                "Nie masz aktywnych przypomnień."
            )

        return (
            "Anulowałem ostatnie przypomnienie."
        )

    return None


def process_command(text):
    global english_mode
    global exam_mode

    set_gui_state("thinking")
    lower = normalize_text(text)

    # Naturalne odwołania do poprzedniej odpowiedzi.
    if lower in (
        "powtórz",
        "powtorz",
        "powiedz jeszcze raz",
        "powiedz to jeszcze raz",
        "co mówiłeś",
        "co mowiles",
    ):
        previous = last_turn()

        if not previous:
            return "Nie mam jeszcze poprzedniej odpowiedzi do powtórzenia."

        print(
            "🎯 INTENT conversation_repeat",
            flush=True,
        )

        return previous["assistant"]

    if any(
        phrase in lower
        for phrase in (
            "powiedz to krócej",
            "powiedz to krocej",
            "streść to",
            "streszcz to",
            "krócej",
            "krocej",
        )
    ):
        previous = last_turn()

        if not previous:
            return "Nie mam jeszcze odpowiedzi, którą mógłbym skrócić."

        print(
            "🎯 INTENT conversation_shorten",
            flush=True,
        )

        return llm_answer(
            "Skróć poniższą poprzednią odpowiedź JARVIS-a. "
            "Zachowaj wszystkie kluczowe fakty i nie dodawaj nowych informacji. "
            "Odpowiedz naturalnie do przeczytania głosowego.\n\n"
            "Poprzednie pytanie użytkownika:\n"
            + previous["user"]
            + "\n\nPoprzednia odpowiedź JARVIS-a:\n"
            + previous["assistant"]
        )

    if any(
        phrase in lower
        for phrase in (
            "wyjaśnij to inaczej",
            "wyjasnij to inaczej",
            "rozwiń to",
            "rozwin to",
            "wytłumacz to inaczej",
            "wytlumacz to inaczej",
        )
    ):
        previous = last_turn()

        if not previous:
            return "Nie mam jeszcze odpowiedzi, do której mogę się odwołać."

        print(
            "🎯 INTENT conversation_rephrase",
            flush=True,
        )

        return llm_answer(
            "Odnieś się wyłącznie do poprzedniej rozmowy poniżej. "
            "Wyjaśnij odpowiedź inaczej lub szerzej zgodnie z poleceniem użytkownika. "
            "Nie zmieniaj faktów pochodzących z lokalnych danych.\n\n"
            "Polecenie użytkownika:\n"
            + text
            + "\n\nPoprzednie pytanie:\n"
            + previous["user"]
            + "\n\nPoprzednia odpowiedź:\n"
            + previous["assistant"]
        )

    if any(
        phrase in lower
        for phrase in (
            "status rozpoznawania głosu",
            "status rozpoznawania glosu",
            "czy rozpoznajesz mój głos",
            "czy rozpoznajesz moj glos",
            "czy rozpoznawanie głosu działa",
            "czy rozpoznawanie glosu dziala",
        )
    ):
        status = speaker_profile_status()

        print(
            "🎯 INTENT speaker_status",
            flush=True,
        )

        if status.get("error"):
            return (
                "Rozpoznawanie głosu zgłasza błąd: "
                + status["error"]
            )

        if not status.get("enrolled"):
            return (
                "Nie mam jeszcze zapisanego profilu twojego głosu."
            )

        if not status.get("enabled"):
            return (
                "Profil twojego głosu jest zapisany, "
                "ale weryfikacja jest obecnie wyłączona."
            )

        return (
            "Rozpoznawanie twojego głosu jest aktywne. "
            f"Profil ma {status.get('samples', '?')} próbek, "
            f"a próg zgodności wynosi "
            f"{status.get('threshold', 0):.2f}."
        )

    # Historia rozmowy - osobna od jawnej pamięci użytkownika.
    if any(
        phrase in lower
        for phrase in (
            "pokaż historię rozmowy",
            "pokaz historie rozmowy",
            "co ostatnio mówiłeś",
            "co ostatnio mowiles",
            "co mi wcześniej odpowiedziałeś",
            "co mi wczesniej odpowiedziales",
        )
    ):
        return format_recent_history(
            limit=6
        )

    if any(
        phrase in lower
        for phrase in (
            "wyczyść historię rozmowy",
            "wyczysc historie rozmowy",
            "usuń historię rozmowy",
            "usun historie rozmowy",
        )
    ):
        clear_history()
        return "Wyczyściłem historię tej rozmowy."

    # Pamięć.
    answer = process_memory_command(
        text,
        lower,
    )

    if answer:
        return answer

    # Przypomnienia.
    answer = process_reminder_command(
        text,
        lower,
    )

    if answer:
        return answer

    # Dojazd ma pierwszeństwo przed ogólnym pytaniem o plan zajęć.
    # Obsługuje naturalne warianty wypowiedzi głosowej.
    commute_words = (
        "wyjść",
        "wyjsc",
        "wychodz",
        "dojad",
        "dojech",
        "dojazd",
    )

    commute_destinations = (
        "uczeln",
        "zaję",
        "zaje",
        "na pk",
        "z domu",
        "domu",
    )

    if (
        any(
            word in lower
            for word in commute_words
        )
        and any(
            word in lower
            for word in commute_destinations
        )
    ):
        day_offset = (
            1
            if "jutro" in lower
            else 0
        )

        print(
            "🎯 INTENT "
            + (
                "commute_tomorrow"
                if day_offset == 1
                else "commute_today"
            ),
            flush=True,
        )

        return trip_to_first_class(
            day_offset=day_offset
        )

    # Prywatny plan zajęć ma pierwszeństwo przed ogólnym LLM.
    # Router porównuje naturalne pytanie z realnymi wydarzeniami ICS,
    # więc obsługuje m.in. "kiedy będę miał ... w laboratorium?".
    calendar_answer = answer_calendar_question(
        text,
        context_turns=recent_turns(
            limit=3
        ),
    )

    if calendar_answer:
        return calendar_answer

    # Odporny router komend głosowych.
    # Whisper może np. zgubić polski znak albo lekko przekręcić frazę.
    voice_intent = classify_voice_intent(text)

    if voice_intent.name != "unknown":
        print(
            f"🎯 INTENT {voice_intent.name} "
            f"({voice_intent.score:.2f})",
            flush=True,
        )

    if voice_intent.name == "weather_today":
        return get_weather(tomorrow=False)

    if voice_intent.name == "weather_tomorrow":
        return get_weather(tomorrow=True)

    if voice_intent.name == "time":
        return (
            "Jest "
            + datetime.now(TIMEZONE).strftime("%H:%M")
            + "."
        )

    if voice_intent.name == "today_classes":
        return get_schedule(day_offset=0)

    if voice_intent.name == "tomorrow_classes":
        return get_schedule(day_offset=1)

    if voice_intent.name == "next_class":
        return get_next_class()

    if voice_intent.name == "server_status":
        return system_status()

    if voice_intent.name in (
        "network_status",
        "raid_status",
    ):
        return short_health_text()

    if voice_intent.name == "today_brief":
        return today_brief()

    if voice_intent.name == "tomorrow_brief":
        return tomorrow_brief()

    # Study Mode.
    if (
        "tryb nauki matematyki" in lower
        or "uczmy się matematyki" in lower
        or "uczmy sie matematyki" in lower
    ):
        return _set_study_mode(
            "matematyka"
        )

    if (
        "tryb nauki programowania" in lower
        or "uczmy się programowania" in lower
        or "uczmy sie programowania" in lower
    ):
        return _set_study_mode(
            "programowanie"
        )

    if (
        "tryb nauki angielskiego" in lower
        or "uczmy się angielskiego" in lower
        or "uczmy sie angielskiego" in lower
    ):
        return _set_study_mode(
            "angielski"
        )

    if (
        "wyłącz tryb nauki" in lower
        or "wylacz tryb nauki" in lower
    ):
        return _set_study_mode(
            None
        )

    if "tryb egzaminu" in lower:
        exam_mode = True
        set_gui_state()

        return (
            "Tryb egzaminu włączony. "
            "Będę cię sprawdzał zamiast od razu podawać odpowiedzi."
        )

    if (
        "wyłącz tryb egzaminu" in lower
        or "wylacz tryb egzaminu" in lower
    ):
        exam_mode = False
        set_gui_state()

        return (
            "Tryb egzaminu wyłączony."
        )

    # Tryb językowy.
    if any(
        phrase in lower
        for phrase in (
            "przełącz na angielski",
            "przelacz na angielski",
            "english mode",
        )
    ):
        english_mode = True
        set_gui_state()

        return (
            "English mode enabled."
        )

    if any(
        phrase in lower
        for phrase in (
            "wróć do polskiego",
            "wroc do polskiego",
            "polski tryb",
        )
    ):
        english_mode = False
        set_gui_state()

        return (
            "Wracam do polskiego."
        )

    # Lokalne szybkie komendy.
    if (
        "która godzina" in lower
        or "ktora godzina" in lower
    ):
        return (
            "Jest "
            + datetime.now(
                TIMEZONE
            ).strftime("%H:%M")
            + "."
        )

    if (
        "jaka jest data" in lower
        or "który dzisiaj" in lower
        or "ktory dzisiaj" in lower
    ):
        return (
            "Dzisiaj jest "
            + datetime.now(
                TIMEZONE
            ).strftime("%d.%m.%Y")
            + "."
        )

    if (
        "status serwera" in lower
        or "status raspberry" in lower
        or "temperatura raspberry" in lower
    ):
        return system_status()

    if (
        "docker" in lower
        or "kontener" in lower
    ):
        return docker_status()

    if (
        "pi-hole" in lower
        or "pihole" in lower
    ):
        return pihole_status()

    # Pogoda.
    if "pogod" in lower:
        return get_weather(
            tomorrow=(
                "jutro" in lower
            )
        )

    # Briefingi.
    if any(
        phrase in lower
        for phrase in (
            "dzień dobry jarvis",
            "dzien dobry jarvis",
            "briefing na dzisiaj",
            "co mnie dzisiaj czeka",
        )
    ):
        return today_brief()

    if any(
        phrase in lower
        for phrase in (
            "przygotuj mnie na jutro",
            "briefing na jutro",
            "co mnie jutro czeka",
        )
    ):
        return tomorrow_brief()

    # Dojazd.
    if (
        "o której mam jutro wyjść" in lower
        or "o ktorej mam jutro wyjsc" in lower
        or "jak dojadę jutro na zajęcia" in lower
        or "jak dojade jutro na zajecia" in lower
        or "dojazd jutro na zajęcia" in lower
        or "dojazd jutro na zajecia" in lower
    ):
        return trip_to_first_class(
            day_offset=1
        )

    if (
        "co jedzie z mojego przystanku" in lower
        or "odjazdy z mojego przystanku" in lower
        or "najbliższy autobus" in lower
        or "kiedy mam autobus" in lower
    ):
        return next_departures(
            HOME_STOP,
            limit=5,
        )

    # Kalendarz.
    has_classes = (
        "zaję" in lower
        or "zaje" in lower
        or "uczeln" in lower
        or "na pk" in lower
    )

    if has_classes:
        if (
            "następn" in lower
            or "najbliższ" in lower
            or "kolejn" in lower
        ):
            return get_next_class()

        if "jutro" in lower:
            return get_schedule(
                day_offset=1
            )

        if (
            "dzisiaj" in lower
            or "dziś" in lower
        ):
            return get_schedule(
                day_offset=0
            )

        return get_schedule(
            day_offset=0
        )

    if any(
        phrase in lower
        for phrase in (
            "odśwież indeks materiałów",
            "odswiez indeks materialow",
            "przebuduj indeks materiałów",
            "przebuduj indeks materialow",
        )
    ):
        result = rebuild_study_index(
            force=True
        )

        if result["failed"]:
            return (
                "Odświeżyłem indeks materiałów, "
                f"ale {len(result['failed'])} plików "
                "nie udało się przetworzyć."
            )

        return (
            "Odświeżyłem indeks materiałów. "
            f"Pliki: {result['files']}, "
            f"przeindeksowane: {result['indexed']}."
        )

    if any(
        phrase in lower
        for phrase in (
            "status indeksu materiałów",
            "status indeksu materialow",
            "ile mam materiałów w indeksie",
            "ile mam materialow w indeksie",
        )
    ):
        status = study_index_status()

        if status.get("error"):
            return (
                "Indeks materiałów zgłasza błąd: "
                + status["error"]
            )

        return (
            "Indeks materiałów zawiera "
            f"{status['files']} plików i "
            f"{status['chunks']} fragmentów."
        )

    if any(
        marker in lower
        for marker in (
            "przepytaj mnie z moich materiałów",
            "przepytaj mnie z moich materialow",
            "zrób quiz z moich materiałów",
            "zrob quiz z moich materialow",
        )
    ):
        print(
            "🎯 INTENT study_rag_quiz",
            flush=True,
        )

        return answer_from_study_rag(
            text,
            quiz=True,
        )


    rag_markers = (
        "na podstawie moich materiałów",
        "na podstawie moich materialow",
        "w moich materiałach",
        "w moich materialach",
        "z moich materiałów",
        "z moich materialow",
        "w moich notatkach",
        "z moich notatek",
        "sprawdź w materiałach",
        "sprawdz w materialach",
        "wyszukaj w materiałach",
        "wyszukaj w materialach",
        "co moje materiały mówią",
        "co moje materialy mowia",
    )

    if any(
        marker in lower
        for marker in rag_markers
    ):
        print(
            "🎯 INTENT study_rag",
            flush=True,
        )

        return answer_from_study_rag(
            text
        )

    if (
        "jakie mam materiały" in lower
        or "jakie mam materialy" in lower
        or "pokaż materiały" in lower
        or "pokaz materialy" in lower
    ):
        materials = list_materials()

        if not materials:
            return (
                "Folder materiałów jest pusty. "
                "Wrzuć pliki do katalogu study_materials."
            )

        names = [
            path.name
            for path in materials[:12]
        ]

        return (
            "Masz materiały: "
            + ", ".join(names)
            + "."
        )

    if (
        "przepytaj mnie z" in lower
        or "zrób quiz z" in lower
        or "zrob quiz z" in lower
    ):
        return answer_from_study_material(
            text,
            quiz=True,
        )

    if (
        "ucz mnie z" in lower
        or "wytłumacz mi materiał" in lower
        or "wytlumacz mi material" in lower
        or "omów materiał" in lower
        or "omow material" in lower
    ):
        return answer_from_study_material(
            text,
            quiz=False,
        )

    if (
        "status wifi" in lower
        or "status wi-fi" in lower
        or "status raid" in lower
        or "stan raid" in lower
        or "stan sieci" in lower
    ):
        return short_health_text()

    return llm_answer(text)


SLEEP_COMMANDS = {
    "idź spać",
    "idz spac",
    "uśpij się",
    "uspij sie",
    "przejdź w tryb uśpienia",
    "przejdz w tryb uspienia",
    "tryb uśpienia",
    "tryb uspienia",
}

STANDBY_COMMANDS = {
    "wróć do czuwania",
    "wroc do czuwania",
    "przejdź w tryb czuwania",
    "przejdz w tryb czuwania",
    "tryb czuwania",
}

SHUTDOWN_COMMANDS = {
    "wyłącz się",
    "wylacz sie",
    "wyłącz jarvisa",
    "wylacz jarvisa",
    "wyłącz jarvis",
    "wylacz jarvis",
    "koniec pracy",
    "do widzenia jarvis",
}


def handle_background_events():
    events = (
        background_events.get_all()
    )

    if not events:
        return False

    for event in events:
        text = event.get("text")

        if not text:
            continue

        event_type = event.get("type")

        print(
            f"🔔 ZDARZENIE: "
            f"{event_type}: "
            f"{text}",
            flush=True,
        )

        if event_type == "web_command":
            set_gui_state(
                "thinking",
                last_user=text,
            )

            answer = process_command(text)

            try:
                append_turn(
                    text,
                    answer,
                )
            except Exception as exc:
                print(
                    f"[HISTORY ERROR] {exc}",
                    flush=True,
                )

            speak(answer)
            continue

        speak(text)

    return True


def main():
    sleep_mode = False
    active_until = 0.0
    pending_command = None
    last_interaction = (
        time.monotonic()
    )

    background_events.start()

    print(
        "J.A.R.V.I.S. Prototype v1.3",
        flush=True,
    )

    try:
        prepare_audio()
    except Exception as exc:
        print(
            f"⚠️ Audio start: {exc}",
            flush=True,
        )

    set_gui_state(
        "standby"
    )

    try:
        while True:
            now = time.monotonic()
            active = (
                now <= active_until
            )

            if (
                AUTO_SLEEP_MINUTES > 0
                and not active
                and not sleep_mode
                and (
                    now - last_interaction
                    >= AUTO_SLEEP_MINUTES * 60
                )
            ):
                sleep_mode = True
                set_gui_state(
                    "sleeping"
                )

            # STANDBY / SLEEP:
            # openWakeWord działa lokalnie.
            if not active:
                state = (
                    "sleeping"
                    if sleep_mode
                    else "standby"
                )

                set_gui_state(
                    state
                )

                reason = wait_for_jarvis(
                    tick_callback=(
                        background_events.pending
                    )
                )

                if reason == "tick":
                    handle_background_events()
                    continue

                if reason != "wake":
                    time.sleep(0.5)
                    continue

                was_sleeping = (
                    sleep_mode
                )

                sleep_mode = False

                active_until = (
                    time.monotonic()
                    + SESSION_SECONDS
                )

                last_interaction = (
                    time.monotonic()
                )

                print(
                    "🔵 JARVIS AKTYWNY",
                    flush=True,
                )

                if SINGLE_UTTERANCE_WAKE:
                    set_gui_state(
                        "listening"
                    )

                    pending_command = listen_command(
                        wait_seconds=WAKE_COMMAND_GRACE_SECONDS
                    )

                    if pending_command:
                        print(
                            "⚡ Komenda razem z wake-word.",
                            flush=True,
                        )
                    else:
                        if was_sleeping:
                            speak(
                                "Jestem."
                            )
                        else:
                            speak(
                                "Tak?"
                            )

                        continue
                else:
                    if was_sleeping:
                        speak(
                            "Jestem."
                        )
                    else:
                        speak(
                            "Tak?"
                        )

                    continue

            # Zdarzenie ma pierwszeństwo
            # przed kolejnym blokującym VAD.
            if background_events.pending():
                handle_background_events()

            if pending_command:
                text = pending_command
                pending_command = None
            else:
                text = listen_command(
                    wait_seconds=ACTIVE_LISTEN_TIMEOUT
                )

            if not text:
                # Jedno puste okno nasłuchu kończy aktywną sesję.
                # Wcześniej JARVIS uruchamiał kolejne 12-sekundowe
                # VAD-y aż do końca SESSION_SECONDS.
                active_until = 0.0
                set_gui_state(
                    "standby"
                )
                continue

            last_interaction = (
                time.monotonic()
            )

            active_until = (
                time.monotonic()
                + SESSION_SECONDS
            )

            normalized = (
                normalize_text(text)
            )

            if normalized in SLEEP_COMMANDS:
                speak(
                    "Przechodzę w tryb uśpienia."
                )

                sleep_mode = True
                active_until = 0.0

                set_gui_state(
                    "sleeping"
                )

                continue

            if normalized in STANDBY_COMMANDS:
                speak(
                    "Wracam do czuwania."
                )

                active_until = 0.0

                set_gui_state(
                    "standby"
                )

                continue

            if normalized in SHUTDOWN_COMMANDS:
                speak(
                    "Do zobaczenia."
                )

                set_gui_state(
                    "offline"
                )

                break

            answer = process_command(
                text
            )

            try:
                append_turn(
                    text,
                    answer,
                )
            except Exception as exc:
                print(
                    f"[HISTORY ERROR] {exc}",
                    flush=True,
                )

            speak(
                answer
            )

            if (
                time.monotonic()
                <= active_until
            ):
                set_gui_state(
                    "listening"
                )
            else:
                set_gui_state(
                    "standby"
                )

    finally:
        background_events.stop()


if __name__ == "__main__":
    try:
        main()

    except KeyboardInterrupt:
        background_events.stop()
        set_gui_state(
            "offline"
        )

        print(
            "\nJARVIS zatrzymany.",
            flush=True,
        )
