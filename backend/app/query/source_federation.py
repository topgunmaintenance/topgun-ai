"""Source federation lane.

A small wrapper that performs a similarity search filtered to a single
``SourceFamily``. The federated query engine instantiates one of these
per active family and merges them with rank-fusion.
"""
from __future__ import annotations

from typing import Any

from app.core.source_family import SourceFamily, label_for
from app.retrieval.vector_store import VectorStore
from app.services.ai_provider import get_ai_provider


class SourceFamilyLane:
    """Run similarity search restricted to one source family."""

    def __init__(self, store: VectorStore, family: SourceFamily) -> None:
        self._store = store
        self.family: SourceFamily = family

    @property
    def name(self) -> str:
        return self.family.lower()

    def search(
        self, *, question: str, top_k: int = 8
    ) -> list[dict[str, Any]]:
        provider = get_ai_provider()
        [embedding] = provider.embed([question])
        hits = self._store.similarity_search(
            embedding=embedding,
            top_k=top_k,
            source_families=[self.family],
        )
        return [
            {
                "id": chunk.id,
                "document_id": chunk.document_id,
                "document_title": chunk.metadata.get("title", chunk.document_id),
                "document_type": chunk.metadata.get("type", "UNKNOWN"),
                "source_family": self.family,
                "page": chunk.page_start,
                "char_start": chunk.char_start,
                "char_end": chunk.char_end,
                "source": chunk.source,
                "ocr": chunk.ocr,
                "snippet": chunk.text[:280],
                "score": float(score),
                "lane": self.name,
                "aircraft_model": chunk.metadata.get("aircraft_model"),
                "ata": list(chunk.metadata.get("ata_chapters") or []),
                "components": list(chunk.metadata.get("components") or []),
                "document_code": chunk.metadata.get("document_code"),
                "url": chunk.metadata.get("url"),
                "vendor": chunk.metadata.get("vendor"),
            }
            for chunk, score in hits
        ]


def label_for_lane(family: SourceFamily) -> str:
    return label_for(family)
