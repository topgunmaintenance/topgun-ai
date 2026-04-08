"""Indexer stage.

Writes the document, its chunks, and the chunk embeddings into the
vector store. The MVP uses an in-memory store (``retrieval.vector_store``);
Phase 4 swaps in a Postgres + pgvector implementation with the same
interface.
"""
from __future__ import annotations

from app.core.logging import get_logger
from app.core.source_family import family_for_doc_type
from app.retrieval.vector_store import get_vector_store

log = get_logger(__name__)


class Indexer:
    name = "indexer"

    def run(self, ctx) -> None:  # noqa: ANN001
        store = get_vector_store()
        fields = ctx.extracted_fields
        source_family = (
            fields.get("source_family") or family_for_doc_type(ctx.classified_type)
        )
        store.upsert(
            document_id=ctx.doc_id,
            chunks=ctx.chunks,
            embeddings=ctx.embeddings,
            metadata={
                "title": ctx.title,
                "type": ctx.classified_type,
                "source_family": source_family,
                "aircraft": ctx.aircraft or fields.get("aircraft_model"),
                "aircraft_model": fields.get("aircraft_model"),
                "source": ctx.source,
                "url": fields.get("url"),
                "vendor": fields.get("vendor"),
                "document_code": fields.get("document_code"),
                "revision": fields.get("revision"),
                "ata_chapters": list(fields.get("ata_chapters") or []),
                "components": list(fields.get("components") or []),
                "systems": list(fields.get("systems") or []),
                "service_bulletins": list(fields.get("service_bulletins") or []),
                "captured_at": fields.get("captured_at"),
            },
        )
        ctx.indexed = True
        log.info(
            "indexer: indexed %d chunks for %s (family=%s)",
            len(ctx.chunks),
            ctx.doc_id,
            source_family,
        )
