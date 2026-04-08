"""Document-related request and response schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

DocumentType = Literal[
    "FIM",
    "AMM",
    "IPC",
    "WDM",
    "SB",
    "WORK_ORDER",
    "LOGBOOK",
    "TROUBLESHOOTING",
    "PARTS_CATALOG",
    "INSPECTION_PROGRAM",
    "BROWSER_CAPTURE",
    "UNKNOWN",
]

DocumentStatus = Literal["uploaded", "processing", "indexed", "failed"]


SourceFamily = Literal[
    "FIM",
    "WDM",
    "AMM",
    "IPC",
    "SB",
    "HISTORY",
    "BROWSER",
    "EXTERNAL",
    "OTHER",
]


class DocumentSummary(BaseModel):
    """The shape used in document list views."""

    id: str
    title: str
    type: DocumentType
    source_family: SourceFamily | None = None
    aircraft: str | None = None
    aircraft_model: str | None = None
    source: str | None = None
    url: str | None = None
    vendor: str | None = None
    document_code: str | None = None
    revision: str | None = None
    ata: list[str] = Field(default_factory=list)
    components: list[str] = Field(default_factory=list)
    captured_at: datetime | None = None
    status: DocumentStatus
    pages: int | None = None
    size_mb: float | None = None
    uploaded_at: datetime | None = None
    uploaded_by: str | None = None
    tags: list[str] = Field(default_factory=list)


class IngestionReport(BaseModel):
    """How a document was processed by the ingestion pipeline."""

    parser_backend: str = "unknown"
    page_count: int = 0
    chunk_count: int = 0
    indexed: bool = False
    ocr_applied: bool = False
    ocr_pages: list[int] = Field(default_factory=list)
    ocr_skipped_reason: str | None = None
    extracted_fields: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class ChunkPreview(BaseModel):
    """A short, citable slice of an indexed document."""

    id: str
    page_start: int
    page_end: int
    position: int
    char_start: int
    char_end: int
    char_count: int
    token_estimate: int
    source: str
    ocr: bool
    snippet: str


class DocumentDetail(DocumentSummary):
    summary: str | None = None
    ingestion: IngestionReport | None = None
    chunk_previews: list[ChunkPreview] = Field(default_factory=list)


class DocumentListResponse(BaseModel):
    documents: list[DocumentSummary]
    total: int


class DocumentCreate(BaseModel):
    title: str
    type: DocumentType = "UNKNOWN"
    aircraft: str | None = None
    source: str | None = None
