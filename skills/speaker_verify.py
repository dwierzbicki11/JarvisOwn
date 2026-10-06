import math
import os
import wave
from pathlib import Path

import numpy as np
from dotenv import load_dotenv


BASE_DIR = Path.home() / "jarvis"
load_dotenv(BASE_DIR / ".env")

SPEAKER_VERIFY_ENABLED = os.getenv(
    "SPEAKER_VERIFY_ENABLED",
    "0",
) == "1"

SPEAKER_VERIFY_THRESHOLD = float(
    os.getenv(
        "SPEAKER_VERIFY_THRESHOLD",
        "0.74",
    )
)

SPEAKER_PROFILE_PATH = Path(
    os.getenv(
        "SPEAKER_PROFILE_PATH",
        str(
            BASE_DIR
            / "data"
            / "speaker_profile.npz"
        ),
    )
)


def _read_pcm16_mono(path):
    path = Path(path)

    with wave.open(
        str(path),
        "rb",
    ) as wav:
        channels = wav.getnchannels()
        width = wav.getsampwidth()
        rate = wav.getframerate()
        frames = wav.readframes(
            wav.getnframes()
        )

    if width != 2:
        raise ValueError(
            "Speaker verifier wymaga PCM 16-bit."
        )

    samples = np.frombuffer(
        frames,
        dtype=np.int16,
    ).astype(np.float32)

    if channels > 1:
        samples = samples.reshape(
            -1,
            channels,
        ).mean(
            axis=1
        )

    if rate != 16000:
        raise ValueError(
            "Speaker verifier oczekuje 16 kHz."
        )

    if samples.size == 0:
        raise ValueError(
            "Puste nagranie."
        )

    return samples / 32768.0


def _frame_signal(
    samples,
    frame_size=400,
    hop=160,
):
    if samples.size < frame_size:
        pad = np.zeros(
            frame_size - samples.size,
            dtype=np.float32,
        )
        samples = np.concatenate(
            [
                samples,
                pad,
            ]
        )

    count = (
        1
        + max(
            0,
            (
                samples.size
                - frame_size
            )
            // hop,
        )
    )

    frames = np.empty(
        (
            count,
            frame_size,
        ),
        dtype=np.float32,
    )

    for index in range(count):
        start = index * hop
        frames[index] = samples[
            start:start + frame_size
        ]

    return frames


def _dct_matrix(
    rows,
    cols,
):
    n = np.arange(
        cols,
        dtype=np.float32,
    )
    k = np.arange(
        rows,
        dtype=np.float32,
    )[:, None]

    return np.cos(
        math.pi
        / cols
        * (
            n + 0.5
        )
        * k
    ).astype(
        np.float32
    )


def extract_embedding(path):
    """
    Lekki lokalny voiceprint bez ciężkich modeli ML.

    Używa cech widmowych podobnych do MFCC.
    To bramka pomocnicza, nie identyfikacja biometryczna klasy security.
    """
    samples = _read_pcm16_mono(
        path
    )

    # Pre-emphasis ogranicza wpływ niskich częstotliwości tła.
    emphasized = np.empty_like(
        samples
    )
    emphasized[0] = samples[0]
    emphasized[1:] = (
        samples[1:]
        - 0.97 * samples[:-1]
    )

    frames = _frame_signal(
        emphasized
    )

    window = np.hamming(
        frames.shape[1]
    ).astype(
        np.float32
    )

    frames = frames * window

    rms = np.sqrt(
        np.mean(
            frames * frames,
            axis=1,
        )
        + 1e-9
    )

    # Zostaw bardziej głosowe fragmenty, żeby cisza i tło
    # nie dominowały profilu.
    floor = float(
        np.percentile(
            rms,
            35,
        )
    )
    threshold = max(
        floor * 1.6,
        0.003,
    )

    voiced = frames[
        rms >= threshold
    ]

    if voiced.shape[0] < 6:
        # Jeżeli nagranie jest bardzo ciche, użyj najmocniejszych ramek.
        order = np.argsort(
            rms
        )[::-1]

        keep = order[
            :min(
                max(
                    6,
                    len(order) // 3,
                ),
                len(order),
            )
        ]

        voiced = frames[keep]

    spectrum = np.abs(
        np.fft.rfft(
            voiced,
            n=512,
            axis=1,
        )
    ) ** 2

    freqs = np.fft.rfftfreq(
        512,
        d=1.0 / 16000.0,
    )

    mask = (
        (freqs >= 250.0)
        & (freqs <= 3800.0)
    )

    spectrum = spectrum[:, mask]
    freqs = freqs[mask]

    band_edges = np.linspace(
        250.0,
        3800.0,
        25,
    )

    bands = []

    for left, right in zip(
        band_edges[:-1],
        band_edges[1:],
    ):
        band_mask = (
            (freqs >= left)
            & (freqs < right)
        )

        energy = np.mean(
            spectrum[:, band_mask],
            axis=1,
        )

        bands.append(
            np.log(
                energy + 1e-8
            )
        )

    log_bands = np.stack(
        bands,
        axis=1,
    )

    # Usuń ogólną głośność; interesuje nas kształt głosu.
    log_bands = (
        log_bands
        - np.mean(
            log_bands,
            axis=1,
            keepdims=True,
        )
    )

    dct = _dct_matrix(
        13,
        log_bands.shape[1],
    )

    cepstra = (
        log_bands
        @ dct.T
    )

    cepstra = cepstra[
        :,
        1:13,
    ]

    power_sum = np.sum(
        spectrum,
        axis=1,
    ) + 1e-9

    centroid = (
        np.sum(
            spectrum
            * freqs[None, :],
            axis=1,
        )
        / power_sum
        / 4000.0
    )

    cumulative = np.cumsum(
        spectrum,
        axis=1,
    )

    targets = (
        power_sum * 0.85
    )[:, None]

    roll_index = np.argmax(
        cumulative >= targets,
        axis=1,
    )

    rolloff = (
        freqs[roll_index]
        / 4000.0
    )

    signs = np.signbit(
        voiced
    )

    zcr = np.mean(
        signs[:, 1:]
        != signs[:, :-1],
        axis=1,
    )

    features = np.concatenate(
        [
            np.mean(
                cepstra,
                axis=0,
            ),
            np.std(
                cepstra,
                axis=0,
            ),
            np.array(
                [
                    np.mean(centroid),
                    np.std(centroid),
                    np.mean(rolloff),
                    np.std(rolloff),
                    np.mean(zcr),
                    np.std(zcr),
                ],
                dtype=np.float32,
            ),
        ]
    ).astype(
        np.float32
    )

    norm = float(
        np.linalg.norm(
            features
        )
    )

    if norm <= 1e-8:
        raise ValueError(
            "Nie udało się zbudować voiceprintu."
        )

    return features / norm


def save_profile(
    embeddings,
):
    embeddings = [
        np.asarray(
            item,
            dtype=np.float32,
        )
        for item in embeddings
    ]

    if len(embeddings) < 3:
        raise ValueError(
            "Do profilu potrzeba co najmniej 3 próbek."
        )

    matrix = np.stack(
        embeddings,
        axis=0,
    )

    centroid = np.mean(
        matrix,
        axis=0,
    )

    norm = float(
        np.linalg.norm(
            centroid
        )
    )

    if norm <= 1e-8:
        raise ValueError(
            "Nie udało się utworzyć profilu."
        )

    centroid = (
        centroid / norm
    ).astype(
        np.float32
    )

    similarities = (
        matrix
        @ centroid
    )

    SPEAKER_PROFILE_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    np.savez_compressed(
        SPEAKER_PROFILE_PATH,
        centroid=centroid,
        sample_count=np.array(
            [len(embeddings)],
            dtype=np.int32,
        ),
        enrollment_mean=np.array(
            [
                float(
                    np.mean(
                        similarities
                    )
                )
            ],
            dtype=np.float32,
        ),
        enrollment_min=np.array(
            [
                float(
                    np.min(
                        similarities
                    )
                )
            ],
            dtype=np.float32,
        ),
    )

    return {
        "samples": len(embeddings),
        "mean_similarity": float(
            np.mean(
                similarities
            )
        ),
        "min_similarity": float(
            np.min(
                similarities
            )
        ),
        "path": str(
            SPEAKER_PROFILE_PATH
        ),
    }


def profile_status():
    if not SPEAKER_PROFILE_PATH.exists():
        return {
            "enabled": SPEAKER_VERIFY_ENABLED,
            "enrolled": False,
            "path": str(
                SPEAKER_PROFILE_PATH
            ),
        }

    try:
        data = np.load(
            SPEAKER_PROFILE_PATH
        )

        return {
            "enabled": SPEAKER_VERIFY_ENABLED,
            "enrolled": True,
            "samples": int(
                data[
                    "sample_count"
                ][0]
            ),
            "enrollment_mean": float(
                data[
                    "enrollment_mean"
                ][0]
            ),
            "enrollment_min": float(
                data[
                    "enrollment_min"
                ][0]
            ),
            "threshold": (
                SPEAKER_VERIFY_THRESHOLD
            ),
            "path": str(
                SPEAKER_PROFILE_PATH
            ),
        }

    except Exception as exc:
        return {
            "enabled": SPEAKER_VERIFY_ENABLED,
            "enrolled": False,
            "error": str(exc),
            "path": str(
                SPEAKER_PROFILE_PATH
            ),
        }


def verify_wav(path):
    """
    Zwraca decyzję bramki głosowej.

    Jeżeli weryfikacja jest wyłączona albo profil nie istnieje,
    nie blokujemy użytkownika.
    """
    if not SPEAKER_VERIFY_ENABLED:
        return {
            "accepted": True,
            "enabled": False,
            "reason": "disabled",
        }

    if not SPEAKER_PROFILE_PATH.exists():
        return {
            "accepted": True,
            "enabled": True,
            "enrolled": False,
            "reason": "profile_missing",
        }

    try:
        data = np.load(
            SPEAKER_PROFILE_PATH
        )

        centroid = np.asarray(
            data["centroid"],
            dtype=np.float32,
        )

        embedding = extract_embedding(
            path
        )

        similarity = float(
            np.dot(
                centroid,
                embedding,
            )
        )

        accepted = (
            similarity
            >= SPEAKER_VERIFY_THRESHOLD
        )

        return {
            "accepted": accepted,
            "enabled": True,
            "enrolled": True,
            "similarity": similarity,
            "threshold": (
                SPEAKER_VERIFY_THRESHOLD
            ),
            "reason": (
                "match"
                if accepted
                else "speaker_mismatch"
            ),
        }

    except Exception as exc:
        # Awaria eksperymentalnego filtra nie może wyłączyć JARVIS-a.
        return {
            "accepted": True,
            "enabled": True,
            "reason": "verification_error",
            "error": str(exc),
        }
