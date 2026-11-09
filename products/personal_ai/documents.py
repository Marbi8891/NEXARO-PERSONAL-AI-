"""Documentos de una organización y búsqueda léxica sobre ellos (ADR-0012).

Texto plano troceado en fragmentos y puntuado con BM25 en Python. Sin índice ni dependencias
nuevas: el esquema (`documents`, `document_chunks`) ya existía. El coste es leer los fragmentos
de la organización en cada búsqueda, por eso los límites son bajos (ver constantes).
"""

import hashlib
import math
import re
import sqlite3
import unicodedata
import uuid
from collections import Counter
from dataclasses import dataclass
from typing import Any

MAX_CHARS = 200_000  # por documento
MAX_DOCUMENTS = 100  # activos por organización
CHUNK_CHARS = 1000
SNIPPET_CHARS = 320
STEM_LENGTH = 6  # «contrato», «contratos» y «contrata» comparten raíz
_STOPWORDS = frozenset(
    [
        "el",
        "la",
        "los",
        "las",
        "un",
        "una",
        "unos",
        "unas",
        "de",
        "del",
        "al",
        "y",
        "o",
        "u",
        "en",
        "a",
        "con",
        "por",
        "para",
        "que",
        "se",
        "es",
        "son",
        "su",
        "sus",
        "lo",
        "como",
        "mas",
        "pero",
        "si",
        "no",
        "ya",
        "este",
        "esta",
        "estos",
        "estas",
        "ese",
        "esa",
        "eso",
        "fue",
        "ser",
        "han",
        "hay",
        "muy",
        "tambien",
        "sobre",
        "the",
        "and",
        "of",
        "to",
        "in",
        "is",
        "for",
        "on",
        "with",
    ]
)
_BM25_K1, _BM25_B = 1.5, 0.75


class DocumentError(Exception):
    pass


class DocumentTooLargeError(DocumentError):
    pass


class EmptyDocumentError(DocumentError):
    pass


class DocumentLimitError(DocumentError):
    pass


class DuplicateDocumentError(DocumentError):
    pass


@dataclass(frozen=True)
class Hit:
    document_id: str
    title: str
    ordinal: int
    snippet: str
    score: float
    content: str


def _tokens(text: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", text.lower())
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return [
        w[:STEM_LENGTH] for w in re.findall(r"\w+", folded) if len(w) > 1 and w not in _STOPWORDS
    ]


def split_chunks(text: str, size: int = CHUNK_CHARS) -> list[str]:
    """Trocea por párrafos hasta ~`size` caracteres; un párrafo largo se parte por frases o, si no
    las hay, por longitud."""
    pieces: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(paragraph) <= size:
            pieces.append(paragraph)
            continue
        current = ""
        for sentence in re.split(r"(?<=[.!?])\s+", paragraph):
            while len(sentence) > size:
                if current:
                    pieces.append(current)
                    current = ""
                pieces.append(sentence[:size])
                sentence = sentence[size:]
            if current and len(current) + len(sentence) + 1 > size:
                pieces.append(current)
                current = sentence
            else:
                current = f"{current} {sentence}".strip()
        if current:
            pieces.append(current)

    chunks: list[str] = []
    for piece in pieces:  # agrupa párrafos cortos consecutivos
        if chunks and len(chunks[-1]) + len(piece) + 2 <= size:
            chunks[-1] = f"{chunks[-1]}\n\n{piece}"
        else:
            chunks.append(piece)
    return chunks


def create_document(
    db: sqlite3.Connection,
    organization_id: str,
    created_by: str,
    title: str,
    content: str,
    *,
    source: str | None = None,
    mime_type: str | None = None,
) -> dict[str, Any]:
    """Debe llamarse dentro de una transacción de escritura."""
    text = content.replace("\x00", "").replace("\r\n", "\n").strip()
    if not text:
        raise EmptyDocumentError("El documento está vacío")
    if len(text) > MAX_CHARS:
        raise DocumentTooLargeError(f"El documento supera los {MAX_CHARS} caracteres")
    active = db.execute(
        "SELECT COUNT(*) AS n FROM documents WHERE organization_id = ? AND deleted_at IS NULL",
        (organization_id,),
    ).fetchone()["n"]
    if active >= MAX_DOCUMENTS:
        raise DocumentLimitError(f"Se alcanzó el máximo de {MAX_DOCUMENTS} documentos")
    digest = hashlib.sha256(text.encode()).hexdigest()
    if db.execute(
        "SELECT 1 FROM documents WHERE organization_id = ? AND sha256 = ? AND deleted_at IS NULL",
        (organization_id, digest),
    ).fetchone():
        raise DuplicateDocumentError("Ya existe un documento con ese mismo contenido")

    document_id = str(uuid.uuid4())
    db.execute(
        """
        INSERT INTO documents (id, organization_id, title, source, mime_type, size_bytes, sha256,
                               status, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'processed', ?)
        """,
        (
            document_id,
            organization_id,
            title,
            source,
            mime_type,
            len(text.encode()),
            digest,
            created_by,
        ),
    )
    chunks = split_chunks(text)
    db.executemany(
        """
        INSERT INTO document_chunks
            (id, organization_id, document_id, ordinal, content, token_count)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (str(uuid.uuid4()), organization_id, document_id, i, c, len(c.split()))
            for i, c in enumerate(chunks)
        ],
    )
    return {"id": document_id, "title": title, "chunk_count": len(chunks), "size_bytes": len(text)}


def list_documents(db: sqlite3.Connection, organization_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        """
        SELECT d.id, d.title, d.source, d.size_bytes, d.created_at, u.email AS created_by_email,
               COUNT(c.id) AS chunk_count
        FROM documents d
        LEFT JOIN users u ON u.id = d.created_by
        LEFT JOIN document_chunks c ON c.document_id = d.id
        WHERE d.organization_id = ? AND d.deleted_at IS NULL
        GROUP BY d.id
        ORDER BY d.created_at DESC, d.rowid DESC
        """,
        (organization_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def delete_document(db: sqlite3.Connection, organization_id: str, document_id: str) -> bool:
    """Borrado lógico del documento y físico de sus fragmentos. False si no existe (o ya estaba
    borrado) en esa organización."""
    row = db.execute(
        "SELECT id FROM documents WHERE id = ? AND organization_id = ? AND deleted_at IS NULL",
        (document_id, organization_id),
    ).fetchone()
    if row is None:
        return False
    db.execute("DELETE FROM document_chunks WHERE document_id = ?", (document_id,))
    db.execute(
        "UPDATE documents SET deleted_at = strftime('%Y-%m-%d %H:%M:%S', 'now') WHERE id = ?",
        (document_id,),
    )
    return True


def search(db: sqlite3.Connection, organization_id: str, query: str, limit: int = 5) -> list[Hit]:
    """Los `limit` fragmentos más relevantes (BM25). Sin coincidencias, lista vacía."""
    terms = set(_tokens(query))
    if not terms:
        return []
    rows = db.execute(
        """
        SELECT c.document_id, d.title, c.ordinal, c.content
        FROM document_chunks c JOIN documents d ON d.id = c.document_id
        WHERE c.organization_id = ? AND d.deleted_at IS NULL
        """,
        (organization_id,),
    ).fetchall()
    counted = [(r, Counter(_tokens(r["content"]))) for r in rows]
    if not counted:
        return []
    average = sum(sum(c.values()) for _, c in counted) / len(counted) or 1.0
    total = len(counted)
    frequency = {t: sum(1 for _, c in counted if t in c) for t in terms}

    scored: list[Hit] = []
    for row, counts in counted:
        length = sum(counts.values())
        score = 0.0
        for term in terms:
            tf = counts.get(term, 0)
            if not tf:
                continue
            idf = math.log(1 + (total - frequency[term] + 0.5) / (frequency[term] + 0.5))
            score += (
                idf
                * tf
                * (_BM25_K1 + 1)
                / (tf + _BM25_K1 * (1 - _BM25_B + _BM25_B * length / average))
            )
        if score > 0:
            text = row["content"]
            scored.append(
                Hit(
                    row["document_id"],
                    row["title"],
                    row["ordinal"],
                    text if len(text) <= SNIPPET_CHARS else text[:SNIPPET_CHARS].rstrip() + "…",
                    round(score, 4),
                    text,
                )
            )
    scored.sort(key=lambda h: (-h.score, h.title, h.ordinal))
    return scored[:limit]


_DELIMITER = re.compile(r"<(/?)\s*fragmento", re.IGNORECASE)


def _neutralize(text: str) -> str:
    """Un documento no puede cerrar ni abrir los delimitadores (inyección indirecta)."""
    return _DELIMITER.sub(lambda m: f"&lt;{m.group(1)}fragmento", text)


def build_context(hits: list[Hit]) -> str:
    """Fragmentos numerados y delimitados: el modelo debe tratarlos como datos, no como órdenes."""
    blocks = []
    for i, h in enumerate(hits, 1):
        title = _neutralize(" ".join(h.title.split())).replace('"', "'")
        blocks.append(
            f'<fragmento n="{i}" documento="{title}">\n{_neutralize(h.content)}\n</fragmento>'
        )
    return "\n\n".join(blocks)
