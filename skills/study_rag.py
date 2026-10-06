import hashlib
import re
import sqlite3
from pathlib import Path

from skills.study_materials import (
    extract_text,
    list_materials,
)


BASE_DIR = Path.home() / "jarvis"
DB_PATH = BASE_DIR / "cache" / "study_index.sqlite3"

MAX_CHUNK_CHARS = 1800
CHUNK_OVERLAP = 250


def _connect():
    DB_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    conn = sqlite3.connect(
        DB_PATH,
        timeout=10,
    )
    conn.row_factory = sqlite3.Row

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS indexed_files (
            path TEXT PRIMARY KEY,
            fingerprint TEXT NOT NULL,
            chunks INTEGER NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS study_chunks
        USING fts5(
            path UNINDEXED,
            chunk_no UNINDEXED,
            content,
            tokenize='unicode61 remove_diacritics 2'
        )
        """
    )

    return conn


def _fingerprint(path: Path) -> str:
    stat = path.stat()

    raw = (
        f"{path.resolve()}|"
        f"{stat.st_mtime_ns}|"
        f"{stat.st_size}"
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


def _chunk_text(
    text: str,
    *,
    max_chars=MAX_CHUNK_CHARS,
    overlap=CHUNK_OVERLAP,
):
    """
    Dzieli materiał na zachodzące na siebie fragmenty.
    Preferuje granice akapitów, ale radzi sobie też z długim blokiem tekstu.
    """
    text = re.sub(
        r"\r\n?",
        "\n",
        text or "",
    ).strip()

    if not text:
        return []

    paragraphs = [
        re.sub(
            r"[ \t]+",
            " ",
            part,
        ).strip()
        for part in re.split(
            r"\n\s*\n",
            text,
        )
        if part.strip()
    ]

    chunks = []
    current = ""

    def flush():
        nonlocal current

        value = current.strip()

        if value:
            chunks.append(value)

        current = ""

    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            flush()

            start = 0

            while start < len(paragraph):
                end = min(
                    len(paragraph),
                    start + max_chars,
                )

                chunk = paragraph[
                    start:end
                ].strip()

                if chunk:
                    chunks.append(chunk)

                if end >= len(paragraph):
                    break

                start = max(
                    start + 1,
                    end - overlap,
                )

            continue

        candidate = (
            paragraph
            if not current
            else current + "\n\n" + paragraph
        )

        if len(candidate) <= max_chars:
            current = candidate
            continue

        previous = current
        flush()

        if (
            overlap > 0
            and previous
        ):
            tail = previous[
                -overlap:
            ].strip()

            candidate = (
                tail + "\n\n" + paragraph
                if tail
                else paragraph
            )

            if len(candidate) <= max_chars:
                current = candidate
                continue

        current = paragraph

    flush()
    return chunks


def _query_terms(query: str):
    return [
        token.lower()
        for token in re.findall(
            r"[0-9A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż_+#.-]{2,}",
            query or "",
        )
        if token.strip(".-")
    ]


def rebuild_index(
    *,
    force=False,
):
    """
    Aktualizuje indeks tylko dla nowych/zmienionych plików.
    Nie zapisuje treści poza lokalnym Raspberry Pi.
    """
    materials = list_materials()
    current_paths = {
        str(path.resolve())
        for path in materials
    }

    indexed = 0
    skipped = 0
    failed = []

    with _connect() as conn:
        known_rows = conn.execute(
            """
            SELECT path, fingerprint
            FROM indexed_files
            """
        ).fetchall()

        known = {
            row["path"]: row["fingerprint"]
            for row in known_rows
        }

        removed = (
            set(known)
            - current_paths
        )

        for old_path in removed:
            conn.execute(
                "DELETE FROM study_chunks WHERE path = ?",
                (old_path,),
            )
            conn.execute(
                "DELETE FROM indexed_files WHERE path = ?",
                (old_path,),
            )

        for path in materials:
            resolved = str(
                path.resolve()
            )

            try:
                fingerprint = _fingerprint(
                    path
                )

                if (
                    not force
                    and known.get(resolved)
                    == fingerprint
                ):
                    skipped += 1
                    continue

                text = extract_text(path)
                chunks = _chunk_text(text)

                conn.execute(
                    "DELETE FROM study_chunks WHERE path = ?",
                    (resolved,),
                )

                for index, chunk in enumerate(
                    chunks
                ):
                    conn.execute(
                        """
                        INSERT INTO study_chunks (
                            path,
                            chunk_no,
                            content
                        )
                        VALUES (?, ?, ?)
                        """,
                        (
                            resolved,
                            index,
                            chunk,
                        ),
                    )

                conn.execute(
                    """
                    INSERT INTO indexed_files (
                        path,
                        fingerprint,
                        chunks
                    )
                    VALUES (?, ?, ?)
                    ON CONFLICT(path) DO UPDATE SET
                        fingerprint=excluded.fingerprint,
                        chunks=excluded.chunks
                    """,
                    (
                        resolved,
                        fingerprint,
                        len(chunks),
                    ),
                )

                indexed += 1

            except Exception as exc:
                failed.append(
                    {
                        "path": str(path),
                        "error": str(exc),
                    }
                )

    return {
        "files": len(materials),
        "indexed": indexed,
        "skipped": skipped,
        "removed": len(removed),
        "failed": failed,
    }


def index_status():
    try:
        rebuild_index(
            force=False
        )

        with _connect() as conn:
            files = conn.execute(
                "SELECT COUNT(*) FROM indexed_files"
            ).fetchone()[0]

            chunks = conn.execute(
                "SELECT COUNT(*) FROM study_chunks"
            ).fetchone()[0]

        return {
            "files": int(files),
            "chunks": int(chunks),
            "database": str(DB_PATH),
        }

    except Exception as exc:
        return {
            "files": 0,
            "chunks": 0,
            "database": str(DB_PATH),
            "error": str(exc),
        }


def search_chunks(
    query: str,
    *,
    limit=6,
    material_path=None,
):
    rebuild_index(
        force=False
    )

    terms = _query_terms(query)

    if not terms:
        return []

    # FTS5 OR daje sensowne wyniki także przy naturalnym pytaniu,
    # w którym część słów nie występuje literalnie w notatkach.
    fts_query = " OR ".join(
        '"' + term.replace('"', '""') + '"'
        for term in terms[:24]
    )

    params = [fts_query]
    where = (
        "study_chunks MATCH ?"
    )

    if material_path is not None:
        where += " AND path = ?"
        params.append(
            str(
                Path(
                    material_path
                ).resolve()
            )
        )

    params.append(
        max(
            1,
            min(
                int(limit),
                20,
            ),
        )
    )

    sql = f"""
        SELECT
            path,
            chunk_no,
            content,
            bm25(study_chunks) AS rank
        FROM study_chunks
        WHERE {where}
        ORDER BY rank
        LIMIT ?
    """

    with _connect() as conn:
        rows = conn.execute(
            sql,
            params,
        ).fetchall()

    results = []

    for row in rows:
        path = Path(
            row["path"]
        )

        try:
            display_path = str(
                path.relative_to(
                    BASE_DIR
                    / "study_materials"
                )
            )
        except Exception:
            display_path = path.name

        results.append(
            {
                "path": path,
                "display_path": display_path,
                "chunk_no": int(
                    row["chunk_no"]
                ),
                "content": row["content"],
                "rank": float(
                    row["rank"]
                ),
            }
        )

    return results


def build_context(
    query: str,
    *,
    limit=6,
    max_chars=10000,
    material_path=None,
):
    results = search_chunks(
        query,
        limit=limit,
        material_path=material_path,
    )

    if not results:
        return "", []

    blocks = []
    used = 0
    sources = []

    for result in results:
        label = (
            f"[ŹRÓDŁO: "
            f"{result['display_path']}, "
            f"fragment {result['chunk_no'] + 1}]"
        )

        block = (
            label
            + "\n"
            + result["content"].strip()
        )

        remaining = (
            max_chars - used
        )

        if remaining <= 200:
            break

        if len(block) > remaining:
            block = block[
                :remaining
            ].rstrip()

        blocks.append(block)
        used += (
            len(block) + 2
        )

        source = result[
            "display_path"
        ]

        if source not in sources:
            sources.append(source)

    return (
        "\n\n".join(blocks),
        sources,
    )
