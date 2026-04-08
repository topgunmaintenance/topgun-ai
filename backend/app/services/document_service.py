"""Business logic for documents.

The service is the one place that knows how to:

- list documents (with demo-mode fallback)
- fetch a document by id and assemble the detail view, including the
  ingestion report and a few chunk previews from the vector store
- accept an upload, persist bytes, run the ingestion pipeline, and
  store the resulting metadata so the UI can render it.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.demo_store import DemoStore, get_demo_store
from app.core.logging import get_logger
from app.ingestion.pipeline import IngestionPipeline, IngestionResult
from app.retrieval.vector_store import VectorStore, get_vector_store
from app.utils.text import normalize_whitespace, truncate

log = get_logger(__name__)


class DocumentService:
    def __init__(
        self,
        store: DemoStore,
        pipeline: IngestionPipeline,
        vector_store: VectorStore,
    ) -> None:
        self._store = store
        self._pipeline = pipeline
        self._vector_store = vector_store

    # ------------------------------------------------------------------
    def list(
        self,
        *,
        q: str | None = None,
        doc_type: str | None = None,
        aircraft: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._store.list_documents(q=q, doc_type=doc_type, aircraft=aircraft)

    def get(self, doc_id: str) -> dict[str, Any] | None:
        doc = self._store.get_document(doc_id)
        if not doc:
            return None
        # Attach indexed-chunk previews from the vector store. The seeded
        # demo documents won't have any (they were never ingested), so
        # this returns an empty list and the UI shows the demo summary.
        previews = self._chunk_previews(doc_id, limit=6)
        if previews:
            doc.setdefault("chunk_previews", previews)
        # Backfill an ingestion report from the in-store record if present.
        if "ingestion" not in doc and previews:
            doc["ingestion"] = {
                "parser_backend": previews[0]["source"],
                "page_count": doc.get("pages", 0) or 0,
                "chunk_count": self._vector_store.chunk_count(doc_id),
                "indexed": True,
                "ocr_applied": any(p["ocr"] for p in previews),
                "ocr_pages": [],
                "extracted_fields": {},
            }
        return doc

    # ------------------------------------------------------------------
    def ingest_upload(
        self,
        *,
        filename: str,
        payload: bytes,
        title: str | None,
        doc_type: str,
        aircraft: str | None,
        source: str | None,
    ) -> dict[str, Any]:
        settings = get_settings()
        if len(payload) > settings.ingestion_max_mb * 1024 * 1024:
            raise ValueError(
                f"upload exceeds max size {settings.ingestion_max_mb} MB"
            )

        upload_dir: Path = settings.upload_dir
        upload_dir.mkdir(parents=True, exist_ok=True)

        digest = hashlib.sha256(payload).hexdigest()[:16]
        doc_id = f"doc_{digest}"
        dest = upload_dir / f"{doc_id}_{filename}"
        dest.write_bytes(payload)

        log.info("upload stored: %s (%d bytes)", dest, len(payload))

        result = self._pipeline.run(
            doc_id=doc_id,
            source_path=dest,
            title=title or filename,
            doc_type=doc_type,
            aircraft=aircraft,
            source=source,
        )

        status = self._status_from(result)
        doc = {
            "id": doc_id,
            "title": title or filename,
            "type": result.classified_type,
            "aircraft": aircraft
            or _first(result.extracted_fields.get("tail_numbers")),
            "source": source,
            "status": status,
            "pages": result.page_count,
            "size_mb": round(len(payload) / (1024 * 1024), 2),
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "uploaded_by": "api_upload",
            "tags": _tags_for(result),
            "summary": result.summary,
            "ingestion": _report_dict(result),
            "chunk_previews": self._chunk_previews(doc_id, limit=6),
        }
        self._store.upsert_document(doc)
        return doc

    # ------------------------------------------------------------------
    def _chunk_previews(self, doc_id: str, *, limit: int) -> list[dict[str, Any]]:
        chunks = self._vector_store.list_chunks(doc_id)[:limit]
        return [
            {
                "id": c.id,
                "page_start": c.page_start,
                "page_end": c.page_end,
                "position": c.position,
                "char_start": c.char_start,
                "char_end": c.char_end,
                "char_count": c.char_count,
                "token_estimate": c.token_estimate,
                "source": c.source,
                "ocr": c.ocr,
                "snippet": truncate(normalize_whitespace(c.text), 320),
            }
            for c in chunks
        ]

    @staticmethod
    def _status_from(result: IngestionResult) -> str:
        if result.error:
            return "failed"
        if result.indexed and result.chunk_count > 0:
            return "indexed"
        if result.page_count > 0:
            return "processing"
        return "failed"


# ---------------------------------------------------------------------------
def _report_dict(result: IngestionResult) -> dict[str, Any]:
    return {
        "parser_backend": result.parser_backend,
        "page_count": result.page_count,
        "chunk_count": result.chunk_count,
        "indexed": result.indexed,
        "ocr_applied": result.ocr_applied,
        "ocr_pages": list(result.ocr_pages),
        "ocr_skipped_reason": result.extracted_fields.get("ocr_skipped_reason"),
        "extracted_fields": {
            k: v
            for k, v in result.extracted_fields.items()
            if k
            in {
                "tail_numbers",
                "ata_chapters",
                "part_numbers",
                "dates",
            }
        },
        "error": result.error,
    }


def _tags_for(result: IngestionResult) -> list[str]:
    tags: list[str] = ["uploaded"]
    if result.ocr_applied:
        tags.append("ocr")
    if result.error:
        tags.append("failed")
    chapters = result.extracted_fields.get("ata_chapters") or []
    for chapter in chapters[:2]:
        tags.append(f"ATA {chapter}")
    return tags


def _first(values: list[str] | None) -> str | None:
    if values:
        return values[0]
    return None


# ---------------------------------------------------------------------------
def get_document_service() -> DocumentService:
    return DocumentService(
        store=get_demo_store(),
        pipeline=IngestionPipeline.default(),
        vector_store=get_vector_store(),
    )
