"""Ingestion pipeline orchestration.

The pipeline is a linear sequence of small stages. Each stage mutates a
shared ``IngestionContext`` and returns it. Stages are intentionally
dumb — they do one thing — so they can be unit-tested in isolation and
swapped when a better implementation lands.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from app.ingestion.chunker import Chunker
from app.ingestion.document_classifier import DocumentClassifier
from app.ingestion.embedder import Embedder
from app.ingestion.field_extractor import FieldExtractor
from app.ingestion.indexer import Indexer
from app.ingestion.ocr_processor import OcrProcessor
from app.ingestion.pdf_parser import PdfParser

log = get_logger(__name__)


class IngestionError(RuntimeError):
    def __init__(self, stage: str, reason: str, *, recoverable: bool = False) -> None:
        super().__init__(f"{stage}: {reason}")
        self.stage = stage
        self.reason = reason
        self.recoverable = recoverable


@dataclass
class IngestionContext:
    doc_id: str
    source_path: Path
    title: str
    declared_type: str = "UNKNOWN"
    aircraft: str | None = None
    source: str | None = None

    # Filled by stages
    pages: list[str] = field(default_factory=list)
    page_extractions: list[dict[str, Any]] = field(default_factory=list)
    classified_type: str = "UNKNOWN"
    extracted_fields: dict[str, Any] = field(default_factory=dict)
    chunks: list[dict[str, Any]] = field(default_factory=list)
    embeddings: list[list[float]] = field(default_factory=list)
    indexed: bool = False


@dataclass
class IngestionResult:
    doc_id: str
    classified_type: str
    page_count: int
    chunk_count: int
    indexed: bool
    parser_backend: str = "unknown"
    ocr_applied: bool = False
    ocr_pages: list[int] = field(default_factory=list)
    extracted_fields: dict[str, Any] = field(default_factory=dict)
    summary: str | None = None
    error: str | None = None


class IngestionPipeline:
    """Orchestrates the stages in order and surfaces a summary result."""

    def __init__(
        self,
        *,
        parser: PdfParser,
        ocr: OcrProcessor,
        classifier: DocumentClassifier,
        extractor: FieldExtractor,
        chunker: Chunker,
        embedder: Embedder,
        indexer: Indexer,
    ) -> None:
        self.parser = parser
        self.ocr = ocr
        self.classifier = classifier
        self.extractor = extractor
        self.chunker = chunker
        self.embedder = embedder
        self.indexer = indexer

    # ------------------------------------------------------------------
    @classmethod
    def default(cls) -> "IngestionPipeline":
        return cls(
            parser=PdfParser(),
            ocr=OcrProcessor(),
            classifier=DocumentClassifier(),
            extractor=FieldExtractor(),
            chunker=Chunker(),
            embedder=Embedder(),
            indexer=Indexer(),
        )

    # ------------------------------------------------------------------
    def run(
        self,
        *,
        doc_id: str,
        source_path: Path,
        title: str,
        doc_type: str = "UNKNOWN",
        aircraft: str | None = None,
        source: str | None = None,
    ) -> IngestionResult:
        ctx = IngestionContext(
            doc_id=doc_id,
            source_path=source_path,
            title=title,
            declared_type=doc_type,
            aircraft=aircraft,
            source=source,
        )
        log.info("ingesting %s (%s)", doc_id, source_path.name)

        try:
            self.parser.run(ctx)
            if self._needs_ocr(ctx):
                self.ocr.run(ctx)
            self.classifier.run(ctx)
            self.extractor.run(ctx)
            self.chunker.run(ctx)
            self.embedder.run(ctx)
            self.indexer.run(ctx)
        except IngestionError as exc:
            log.error(
                "ingestion failed at %s: %s (recoverable=%s)",
                exc.stage,
                exc.reason,
                exc.recoverable,
            )
            return IngestionResult(
                doc_id=doc_id,
                classified_type=ctx.classified_type or "UNKNOWN",
                page_count=len(ctx.pages),
                chunk_count=len(ctx.chunks),
                indexed=False,
                parser_backend=ctx.extracted_fields.get("parser_backend", "unknown"),
                ocr_applied=bool(ctx.extracted_fields.get("ocr_applied")),
                ocr_pages=list(ctx.extracted_fields.get("ocr_pages", [])),
                extracted_fields=dict(ctx.extracted_fields),
                summary=f"Failed at {exc.stage}: {exc.reason}",
                error=f"{exc.stage}: {exc.reason}",
            )

        return IngestionResult(
            doc_id=doc_id,
            classified_type=ctx.classified_type,
            page_count=len(ctx.pages),
            chunk_count=len(ctx.chunks),
            indexed=ctx.indexed,
            parser_backend=ctx.extracted_fields.get("parser_backend", "unknown"),
            ocr_applied=bool(ctx.extracted_fields.get("ocr_applied")),
            ocr_pages=list(ctx.extracted_fields.get("ocr_pages", [])),
            extracted_fields=dict(ctx.extracted_fields),
            summary=_summary(ctx),
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _needs_ocr(ctx: IngestionContext) -> bool:
        """Run OCR if any page is empty/low-text or no pages came back."""
        if not ctx.pages:
            return True
        if any(info.get("needs_ocr") for info in ctx.page_extractions):
            return True
        # Defensive fallback for parsers that didn't populate extractions.
        if not ctx.page_extractions:
            average = sum(len(p) for p in ctx.pages) / max(len(ctx.pages), 1)
            return average < 40
        return False


def _summary(ctx: IngestionContext) -> str:
    aircraft = ctx.aircraft or ctx.extracted_fields.get("aircraft") or "unspecified"
    return (
        f"Ingested {len(ctx.pages)} pages as {ctx.classified_type} "
        f"for {aircraft}; produced {len(ctx.chunks)} chunks."
    )
