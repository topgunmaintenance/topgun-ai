"""Pluggable vector store interface.

The MVP ships a tiny in-memory implementation so the end-to-end flow
(ingestion → retrieval → query) works without Postgres. Phase 1 adds a
pgvector-backed implementation with the same surface area.
"""
from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class StoredChunk:
    id: str
    document_id: str
    text: str
    page_start: int
    page_end: int
    position: int
    embedding: list[float]
    char_start: int = 0
    char_end: int = 0
    char_count: int = 0
    token_estimate: int = 0
    content_hash: str = ""
    source: str = "unknown"
    ocr: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class VectorStore(Protocol):
    def upsert(
        self,
        *,
        document_id: str,
        chunks: list[dict[str, Any]],
        embeddings: list[list[float]],
        metadata: dict[str, Any],
    ) -> None: ...

    def similarity_search(
        self,
        *,
        embedding: list[float],
        top_k: int = 10,
        doc_types: list[str] | None = None,
        source_families: list[str] | None = None,
    ) -> list[tuple[StoredChunk, float]]: ...

    def list_chunks(self, document_id: str) -> list[StoredChunk]: ...

    def chunk_count(self, document_id: str) -> int: ...

    def delete_document(self, document_id: str) -> int: ...

    def all_metadata(self) -> list[dict[str, Any]]: ...


# ---------------------------------------------------------------------------
class MemoryVectorStore:
    """Thread-safe, in-process vector store. Cosine similarity."""

    def __init__(self) -> None:
        self._chunks: dict[str, StoredChunk] = {}
        self._lock = threading.Lock()

    def upsert(
        self,
        *,
        document_id: str,
        chunks: list[dict[str, Any]],
        embeddings: list[list[float]],
        metadata: dict[str, Any],
    ) -> None:
        with self._lock:
            # Drop any prior chunks for the same document.
            self._chunks = {
                cid: c for cid, c in self._chunks.items() if c.document_id != document_id
            }
            for chunk, vec in zip(chunks, embeddings):
                stored = StoredChunk(
                    id=chunk["id"],
                    document_id=document_id,
                    text=chunk["text"],
                    page_start=chunk["page_start"],
                    page_end=chunk["page_end"],
                    position=chunk["position"],
                    embedding=vec,
                    char_start=chunk.get("char_start", 0),
                    char_end=chunk.get("char_end", 0),
                    char_count=chunk.get("char_count", len(chunk.get("text", ""))),
                    token_estimate=chunk.get("token_estimate", 0),
                    content_hash=chunk.get("content_hash", ""),
                    source=chunk.get("source", "unknown"),
                    ocr=bool(chunk.get("ocr", False)),
                    metadata=dict(metadata),
                )
                self._chunks[stored.id] = stored

    def similarity_search(
        self,
        *,
        embedding: list[float],
        top_k: int = 10,
        doc_types: list[str] | None = None,
        source_families: list[str] | None = None,
    ) -> list[tuple[StoredChunk, float]]:
        with self._lock:
            candidates = list(self._chunks.values())
        if doc_types:
            allowed_types = set(doc_types)
            candidates = [
                c for c in candidates if c.metadata.get("type") in allowed_types
            ]
        if source_families:
            allowed_families = set(source_families)
            candidates = [
                c
                for c in candidates
                if c.metadata.get("source_family") in allowed_families
            ]

        scored = [
            (c, _cosine(c.embedding, embedding)) for c in candidates if c.embedding
        ]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:top_k]

    def all_metadata(self) -> list[dict[str, Any]]:
        """Return one metadata dict per indexed *document*."""
        with self._lock:
            seen: dict[str, dict[str, Any]] = {}
            for c in self._chunks.values():
                if c.document_id not in seen:
                    seen[c.document_id] = {
                        "document_id": c.document_id,
                        **c.metadata,
                    }
            return list(seen.values())

    def list_chunks(self, document_id: str) -> list[StoredChunk]:
        with self._lock:
            return sorted(
                (c for c in self._chunks.values() if c.document_id == document_id),
                key=lambda c: (c.page_start, c.position),
            )

    def chunk_count(self, document_id: str) -> int:
        with self._lock:
            return sum(1 for c in self._chunks.values() if c.document_id == document_id)

    def delete_document(self, document_id: str) -> int:
        with self._lock:
            before = len(self._chunks)
            self._chunks = {
                cid: c for cid, c in self._chunks.items() if c.document_id != document_id
            }
            return before - len(self._chunks)


# ---------------------------------------------------------------------------
def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    global _store
    if _store is None:
        _store = MemoryVectorStore()
    return _store
