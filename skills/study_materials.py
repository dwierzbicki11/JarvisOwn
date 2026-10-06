import hashlib
import re
import subprocess
from pathlib import Path

BASE_DIR = Path.home() / "jarvis"
MATERIALS_DIR = BASE_DIR / "study_materials"
CACHE_DIR = BASE_DIR / "cache" / "study_materials"

MATERIALS_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

SUPPORTED = {
    ".txt",
    ".md",
    ".pdf",
    ".py",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".java",
}


def list_materials():
    return [
        path
        for path in sorted(MATERIALS_DIR.rglob("*"))
        if path.is_file()
        and path.suffix.lower() in SUPPORTED
    ]


def _cache_path(path):
    stat = path.stat()
    token = (
        f"{path.resolve()}|"
        f"{stat.st_mtime_ns}|"
        f"{stat.st_size}"
    )

    digest = hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()[:24]

    return CACHE_DIR / f"{digest}.txt"


def _extract_pdf(path):
    result = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip()
            or "pdftotext nie powiódł się"
        )

    return result.stdout


def extract_text(path):
    path = Path(path)
    cache = _cache_path(path)

    if cache.exists():
        return cache.read_text(
            encoding="utf-8",
            errors="ignore",
        )

    if path.suffix.lower() == ".pdf":
        text = _extract_pdf(path)
    else:
        text = path.read_text(
            encoding="utf-8",
            errors="ignore",
        )

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text).strip()

    cache.write_text(
        text,
        encoding="utf-8",
    )

    return text


def find_material(name):
    wanted = name.lower().strip()
    exact = []
    partial = []

    for path in list_materials():
        relative = str(
            path.relative_to(MATERIALS_DIR)
        ).lower()

        if (
            relative == wanted
            or path.name.lower() == wanted
            or path.stem.lower() == wanted
        ):
            exact.append(path)

        elif (
            wanted in relative
            or wanted in path.stem.lower()
        ):
            partial.append(path)

    matches = exact or partial
    return matches[0] if matches else None


def material_for_prompt(path, max_chars=14000):
    text = extract_text(path)

    if len(text) <= max_chars:
        return text

    half = max_chars // 2

    return (
        text[:half]
        + "\n\n[... pominięto środek materiału ...]\n\n"
        + text[-half:]
    )


def search_materials(
    query,
    limit=4,
    excerpt_chars=1800,
):
    words = {
        word
        for word in re.findall(
            r"[a-zA-ZąćęłńóśźżĄĆĘŁŃÓŚŹŻ0-9_+#.-]{3,}",
            query.lower(),
        )
    }

    scored = []

    for path in list_materials():
        try:
            text = extract_text(path)
        except Exception:
            continue

        lower = text.lower()

        score = sum(
            lower.count(word)
            for word in words
        )

        if not words:
            score = 1

        if score <= 0:
            continue

        positions = [
            lower.find(word)
            for word in words
            if lower.find(word) >= 0
        ]

        first_pos = min(positions) if positions else 0
        start = max(0, first_pos - excerpt_chars // 3)

        scored.append(
            (
                score,
                path,
                text[start:start + excerpt_chars],
            )
        )

    scored.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    return [
        {
            "path": path,
            "score": score,
            "excerpt": excerpt,
        }
        for score, path, excerpt in scored[:limit]
    ]
