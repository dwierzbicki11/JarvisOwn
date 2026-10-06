import os
import sys
import tempfile
from pathlib import Path

BASE_DIR = Path.home() / "jarvis"
sys.path.insert(
    0,
    str(BASE_DIR),
)

from dotenv import load_dotenv

from skills.speaker_verify import (
    extract_embedding,
    profile_status,
    save_profile,
)
from skills.speech_vad import (
    record_with_speech_vad,
)


load_dotenv(BASE_DIR / ".env")

SAMPLES = max(
    3,
    int(
        os.getenv(
            "SPEAKER_ENROLL_SAMPLES",
            "5",
        )
    ),
)

PHRASES = (
    "Jarvis, jaka będzie jutro pogoda?",
    "Jarvis, kiedy mam następne zajęcia?",
    "Jarvis, przypomnij mi o nauce.",
    "Jarvis, sprawdź status serwera.",
    "Jarvis, pomóż mi z matematyką.",
)


def main():
    print(
        "=== JARVIS SPEAKER ENROLLMENT ==="
    )
    print(
        "Nagraj kilka próbek normalnym głosem. "
        "Najlepiej w typowych warunkach używania JARVIS-a."
    )

    embeddings = []

    for index in range(SAMPLES):
        phrase = PHRASES[
            index % len(PHRASES)
        ]

        print()
        print(
            f"Próbka {index + 1}/{SAMPLES}"
        )
        print(
            f'Powiedz: "{phrase}"'
        )
        input(
            "Naciśnij ENTER i zacznij mówić..."
        )

        with tempfile.NamedTemporaryFile(
            suffix=".wav",
            delete=False,
        ) as tmp:
            wav_path = Path(
                tmp.name
            )

        try:
            recorded = (
                record_with_speech_vad(
                    str(wav_path),
                    wait_seconds=15,
                )
            )

            if not recorded:
                print(
                    "Nie udało się nagrać tej próbki. "
                    "Powtórz ją."
                )
                continue

            embedding = extract_embedding(
                wav_path
            )

            embeddings.append(
                embedding
            )

            print(
                "✅ Próbka przyjęta."
            )

        except Exception as exc:
            print(
                "❌ Błąd próbki: "
                + str(exc)
            )

        finally:
            try:
                wav_path.unlink()
            except OSError:
                pass

    if len(embeddings) < 3:
        raise SystemExit(
            "Za mało poprawnych próbek. "
            "Uruchom enrolment ponownie."
        )

    result = save_profile(
        embeddings
    )

    print()
    print(
        "✅ Profil głosu zapisany."
    )
    print(
        f"Próbki: {result['samples']}"
    )
    print(
        "Spójność średnia: "
        f"{result['mean_similarity']:.3f}"
    )
    print(
        "Najniższa spójność: "
        f"{result['min_similarity']:.3f}"
    )
    print(
        "Plik: "
        + result["path"]
    )
    print()
    print(
        "Aby włączyć bramkę, ustaw w ~/jarvis/.env:"
    )
    print(
        "SPEAKER_VERIFY_ENABLED=1"
    )
    print(
        "Domyślny próg: "
        "SPEAKER_VERIFY_THRESHOLD=0.74"
    )

    status = profile_status()

    if status.get("error"):
        print(
            "⚠️ Status profilu: "
            + status["error"]
        )


if __name__ == "__main__":
    main()
