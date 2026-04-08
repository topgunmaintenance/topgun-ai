"""Browser-assisted manual connector.

Topgun AI is designed to plug into manual sources the operator is
*already* logged into in their dedicated browser. We deliberately do
**not** scrape the open internet — every browser-derived document
arrives via an explicit push from one of three transports:

1. **Browser extension** — a small extension running in the operator's
   own browser invokes ``POST /api/connectors/browser/push`` with the
   visible page text and metadata when the operator clicks "send to
   Topgun AI".
2. **Local API handoff** — the operator runs a small CLI / GUI helper
   that does the same POST without an extension installed.
3. **Future Playwright-controlled mode** — a connector configured by
   IT can drive Playwright against an authorized portal in headed
   mode (still using the operator's session). The same push handler
   ingests the result.

This module ships:

- :class:`BrowserPushPayload` — the dataclass that mirrors the API body.
- :class:`BrowserPushIngestor` — the bridge that runs the ingestion
  pipeline against pushed text and stores it in the vector store.
- :class:`BrowserPushedConnector` — implements the :class:`Connector`
  protocol so the federated query engine can include browser-derived
  hits in its lane fan-out, even though they were pre-ingested by the
  push step (rather than fetched on demand).

The on-demand search via Playwright is intentionally *not* implemented
in this phase — but the interface is shaped so adding it later doesn't
change any caller.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.connectors.base import Connector, ConnectorHit
from app.core.logging import get_logger
from app.ingestion.pipeline import IngestionPipeline, IngestionResult
from app.retrieval.vector_store import VectorStore

log = get_logger(__name__)


# ---------------------------------------------------------------------------
@dataclass
class BrowserPushPayload:
    """The shape the push endpoint accepts.

    All fields are optional except ``text`` and ``title``. The push
    handler fills in sensible defaults for the rest, and the field
    extractor will recover most of them from the text body anyway.
    """

    title: str
    text: str
    url: str | None = None
    aircraft: str | None = None
    document_code: str | None = None
    revision: str | None = None
    vendor: str | None = None
    declared_type: str = "BROWSER_CAPTURE"
    captured_at: datetime | None = None
    notes: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
class BrowserPushIngestor:
    """Persist a browser push as an indexed document.

    The ingestor:

    - writes the pushed text to a temp file under the upload dir,
    - runs the standard :class:`IngestionPipeline` against it,
    - upserts a document record into the demo store with all the
      browser-specific metadata so the UI can show the URL, vendor,
      and capture timestamp.

    By going through the same pipeline as PDF uploads we get document
    classification, field extraction, chunking, embedding, and indexing
    "for free" — including OCR-skip metadata, since text input never
    needs OCR.
    """

    def __init__(
        self,
        *,
        pipeline: IngestionPipeline,
        upload_dir: Path,
        vector_store: VectorStore,
    ) -> None:
        self._pipeline = pipeline
        self._upload_dir = upload_dir
        self._vector_store = vector_store

    # ------------------------------------------------------------------
    def ingest(self, payload: BrowserPushPayload) -> dict[str, Any]:
        captured_at = payload.captured_at or datetime.now(timezone.utc)
        text = payload.text or ""
        if not text.strip():
            raise ValueError("browser push payload has no text body")

        digest = hashlib.sha256(
            (payload.url or "") .encode("utf-8") + text.encode("utf-8")
        ).hexdigest()[:16]
        doc_id = f"browser_{digest}"

        self._upload_dir.mkdir(parents=True, exist_ok=True)
        path = self._upload_dir / f"{doc_id}.txt"
        # Prepend a tiny header so the field extractor can recover the
        # URL / title / vendor without depending on the API caller.
        header = self._header(payload, captured_at)
        path.write_text(header + "\n\n" + text)

        result: IngestionResult = self._pipeline.run(
            doc_id=doc_id,
            source_path=path,
            title=payload.title,
            doc_type=payload.declared_type,
            aircraft=payload.aircraft,
            source=payload.vendor or "browser_push",
        )

        # Patch the metadata that lives on the vector store with the
        # browser-specific fields the pipeline doesn't know about.
        self._patch_metadata(
            doc_id=doc_id,
            url=payload.url,
            vendor=payload.vendor,
            captured_at=captured_at,
            document_code=payload.document_code,
            revision=payload.revision,
        )

        log.info(
            "browser_push: ingested doc=%s chunks=%d url=%s",
            doc_id,
            result.chunk_count,
            payload.url,
        )

        return {
            "doc_id": doc_id,
            "title": payload.title,
            "url": payload.url,
            "vendor": payload.vendor,
            "captured_at": captured_at.isoformat(),
            "ingestion": {
                "parser_backend": result.parser_backend,
                "page_count": result.page_count,
                "chunk_count": result.chunk_count,
                "indexed": result.indexed,
                "error": result.error,
                "extracted_fields": dict(result.extracted_fields),
            },
        }

    # ------------------------------------------------------------------
    @staticmethod
    def _header(payload: BrowserPushPayload, captured_at: datetime) -> str:
        parts = [
            f"BROWSER CAPTURE — {payload.title}",
            f"URL: {payload.url}" if payload.url else "URL: (not provided)",
            f"VENDOR: {payload.vendor}" if payload.vendor else "",
            f"DOCUMENT_CODE: {payload.document_code}" if payload.document_code else "",
            f"REVISION: {payload.revision}" if payload.revision else "",
            f"CAPTURED_AT: {captured_at.isoformat()}",
        ]
        return "\n".join(p for p in parts if p)

    def _patch_metadata(
        self,
        *,
        doc_id: str,
        url: str | None,
        vendor: str | None,
        captured_at: datetime,
        document_code: str | None,
        revision: str | None,
    ) -> None:
        # Reach into the vector store and patch each chunk's metadata
        # in place. The MemoryVectorStore exposes ``list_chunks`` which
        # returns live references in this implementation.
        chunks = self._vector_store.list_chunks(doc_id)
        patch = {
            "url": url,
            "vendor": vendor,
            "captured_at": captured_at.isoformat(),
            "document_code": document_code,
            "revision": revision,
            "source_family": "BROWSER",
        }
        for c in chunks:
            c.metadata.update({k: v for k, v in patch.items() if v is not None})


# ---------------------------------------------------------------------------
class BrowserPushedConnector:
    """Connector view over already-ingested browser captures.

    Browser pushes are *pre-ingested*, so this connector doesn't fetch
    anything at query time — it just exposes the federation interface
    so the query engine can call ``connector.search(...)`` uniformly
    across local docs and external sources.

    The actual ranked results come straight out of the vector store via
    a similarity search filtered to ``source_family=BROWSER``. We use
    the same embedding provider as the local lanes for consistency.
    """

    name = "browser_pushed"
    enabled = True

    def __init__(self, vector_store: VectorStore) -> None:
        self._store = vector_store

    def search(
        self,
        *,
        question: str,
        intent: Any,
        top_k: int = 6,
    ) -> list[ConnectorHit]:
        # Lazy import to avoid a cycle with services/ai_provider.
        from app.services.ai_provider import get_ai_provider

        provider = get_ai_provider()
        [embedding] = provider.embed([question])
        hits = self._store.similarity_search(
            embedding=embedding,
            top_k=top_k,
            source_families=["BROWSER"],
        )
        out: list[ConnectorHit] = []
        for chunk, score in hits:
            meta = chunk.metadata
            out.append(
                ConnectorHit(
                    id=chunk.id,
                    document_id=chunk.document_id,
                    document_title=meta.get("title", chunk.document_id),
                    document_type=meta.get("type", "BROWSER_CAPTURE"),
                    snippet=chunk.text[:280],
                    score=float(score),
                    page=chunk.page_start,
                    char_start=chunk.char_start,
                    char_end=chunk.char_end,
                    source_family="BROWSER",
                    url=meta.get("url"),
                    vendor=meta.get("vendor"),
                    metadata={
                        "ata": meta.get("ata_chapters") or [],
                        "components": meta.get("components") or [],
                        "captured_at": meta.get("captured_at"),
                    },
                )
            )
        return out
