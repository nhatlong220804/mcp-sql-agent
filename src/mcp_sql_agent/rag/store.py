"""Document store and retrieval.

Chunks live in the same SQLite file as the business data, in `rag_*` tables that the
schema tools hide. Keeping them together means one file to ship and no second
service to run.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from .chunker import chunk_text
from .embedder import TfidfIndex

SCHEMA = """
CREATE TABLE IF NOT EXISTS rag_documents (
    doc_id      TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    source      TEXT,
    added_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS rag_chunks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id      TEXT NOT NULL REFERENCES rag_documents(doc_id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    text        TEXT NOT NULL,
    UNIQUE (doc_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_rag_chunks_doc ON rag_chunks(doc_id);
"""


@dataclass
class Hit:
    doc_id: str
    title: str
    chunk_index: int
    text: str
    score: float


def _rows(conn: sqlite3.Connection) -> None:
    """Make sure rows come back addressable by column name."""
    if conn.row_factory is not sqlite3.Row:
        conn.row_factory = sqlite3.Row


def ensure_schema(conn: sqlite3.Connection) -> None:
    _rows(conn)
    conn.executescript(SCHEMA)
    conn.commit()


def add_document(
    conn: sqlite3.Connection,
    doc_id: str,
    title: str,
    text: str,
    source: str | None = None,
    chunk_size: int = 512,
    overlap: int = 64,
) -> int:
    """Index one document. Returns the number of chunks written."""
    ensure_schema(conn)
    chunks = chunk_text(text, size=chunk_size, overlap=overlap)
    if not chunks:
        raise ValueError(f"document {doc_id!r} produced no chunks")

    conn.execute(
        "INSERT OR REPLACE INTO rag_documents (doc_id, title, source) VALUES (?, ?, ?)",
        (doc_id, title, source),
    )
    conn.execute("DELETE FROM rag_chunks WHERE doc_id = ?", (doc_id,))
    conn.executemany(
        "INSERT INTO rag_chunks (doc_id, chunk_index, text) VALUES (?, ?, ?)",
        [(doc_id, c.index, c.text) for c in chunks],
    )
    conn.commit()
    return len(chunks)


def list_documents(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    ensure_schema(conn)
    rows = conn.execute(
        """
        SELECT d.doc_id, d.title, d.source, COUNT(c.id) AS chunks
        FROM rag_documents d
        LEFT JOIN rag_chunks c ON c.doc_id = d.doc_id
        GROUP BY d.doc_id
        ORDER BY d.title
        """
    ).fetchall()
    return [dict(r) for r in rows]


def _load_chunks(conn: sqlite3.Connection) -> tuple[list[dict[str, Any]], TfidfIndex | None]:
    ensure_schema(conn)
    rows = conn.execute(
        """
        SELECT c.doc_id, d.title, c.chunk_index, c.text
        FROM rag_chunks c
        JOIN rag_documents d ON d.doc_id = c.doc_id
        ORDER BY c.doc_id, c.chunk_index
        """
    ).fetchall()
    records = [dict(r) for r in rows]
    if not records:
        return [], None
    return records, TfidfIndex([r["text"] for r in records])


def search(conn: sqlite3.Connection, query: str, k: int = 5) -> list[Hit]:
    records, index = _load_chunks(conn)
    if index is None:
        return []
    hits = []
    for row, score in index.search(query, k=k):
        rec = records[row]
        hits.append(
            Hit(
                doc_id=rec["doc_id"],
                title=rec["title"],
                chunk_index=rec["chunk_index"],
                text=rec["text"],
                score=score,
            )
        )
    return hits
