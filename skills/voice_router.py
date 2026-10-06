import os
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path.home() / "jarvis" / ".env")
DEFAULT_THRESHOLD = float(os.getenv("VOICE_INTENT_THRESHOLD", "0.72"))


@dataclass
class VoiceIntent:
    name: str
    score: float = 1.0


def _ascii(text):
    normalized = unicodedata.normalize(
        "NFKD",
        text,
    )

    return "".join(
        ch
        for ch in normalized
        if not unicodedata.combining(ch)
    )


def normalize_voice_text(text):
    text = _ascii(text.lower())
    text = re.sub(
        r"[^a-z0-9+#:\s-]",
        " ",
        text,
    )
    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    # Whisper czasem pozostawia wake-word w komendzie.
    text = re.sub(
        r"^(hej\s+)?jarvis[,\s]+",
        "",
        text,
    ).strip()

    return text


INTENTS = {
    "weather_today": (
        "jaka jest pogoda",
        "jaka pogoda",
        "pogoda dzisiaj",
        "pogoda na dzisiaj",
    ),
    "weather_tomorrow": (
        "jaka bedzie jutro pogoda",
        "pogoda jutro",
        "pogoda na jutro",
    ),
    "time": (
        "ktora godzina",
        "jaka jest godzina",
        "podaj godzine",
    ),
    "today_classes": (
        "jakie mam dzisiaj zajecia",
        "co mam dzisiaj na uczelni",
        "plan zajec na dzisiaj",
    ),
    "tomorrow_classes": (
        "jakie mam jutro zajecia",
        "co mam jutro na uczelni",
        "plan zajec na jutro",
    ),
    "next_class": (
        "jakie mam nastepne zajecia",
        "najblizsze zajecia",
        "co mam nastepne",
    ),
    "server_status": (
        "status serwera",
        "status raspberry",
        "jak dziala serwer",
    ),
    "network_status": (
        "status wifi",
        "status wi fi",
        "stan sieci",
        "jak dziala wifi",
    ),
    "raid_status": (
        "status raid",
        "stan raid",
        "jak dziala raid",
    ),
    "today_brief": (
        "briefing na dzisiaj",
        "co mnie dzisiaj czeka",
        "dzien dobry jarvis",
    ),
    "tomorrow_brief": (
        "briefing na jutro",
        "co mnie jutro czeka",
        "przygotuj mnie na jutro",
    ),
}


def _similarity(left, right):
    if left == right:
        return 1.0

    # Bonus jeśli cała fraza występuje w dłuższym zdaniu.
    if left in right or right in left:
        return 0.96

    return SequenceMatcher(
        None,
        left,
        right,
    ).ratio()


def classify_voice_intent(
    text,
    threshold=DEFAULT_THRESHOLD,
):
    normalized = normalize_voice_text(text)

    best = VoiceIntent(
        name="unknown",
        score=0.0,
    )

    for name, phrases in INTENTS.items():
        for phrase in phrases:
            score = _similarity(
                phrase,
                normalized,
            )

            if score > best.score:
                best = VoiceIntent(
                    name=name,
                    score=score,
                )

    if best.score < threshold:
        return VoiceIntent(
            name="unknown",
            score=best.score,
        )

    return best
