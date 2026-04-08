"""Query workspace request/response schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.common import ConfidenceReport, DocRef
from app.schemas.documents import SourceFamily


class QueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    aircraft: str | None = None
    document_types: list[str] | None = None
    source_families: list[str] | None = None
    sources: list[str] | None = None
    max_citations: int = Field(default=8, ge=1, le=20)


class AnswerSection(BaseModel):
    heading: str
    bullets: list[str] = Field(default_factory=list)
    family: SourceFamily | None = None


class Citation(BaseModel):
    document_id: str
    document_title: str
    document_type: str
    source_family: SourceFamily | None = None
    page: int
    char_start: int = 0
    char_end: int = 0
    snippet: str
    score: float = Field(ge=0.0, le=1.0)
    lane: str = "manual"
    source: str = "unknown"
    aircraft_model: str | None = None
    ata: list[str] = Field(default_factory=list)
    component: str | None = None
    document_code: str | None = None
    url: str | None = None
    vendor: str | None = None
    ocr: bool = False
    weak: bool = False


class QueryIntentSummary(BaseModel):
    raw_question: str | None = None
    aircraft: str | None = None
    symptom: str | None = None
    component_hints: list[str] = Field(default_factory=list)
    system_hints: list[str] = Field(default_factory=list)
    ata_hints: list[str] = Field(default_factory=list)
    intent_kind: str = "general"
    family_priority: list[SourceFamily] = Field(default_factory=list)
    family_weights: dict[str, float] = Field(default_factory=dict)


class CoverageGap(BaseModel):
    family: SourceFamily
    label: str
    reason: str
    vendor_hint: str | None = None


class CoverageReport(BaseModel):
    likely_families: list[SourceFamily] = Field(default_factory=list)
    available_families: list[SourceFamily] = Field(default_factory=list)
    missing_families: list[SourceFamily] = Field(default_factory=list)
    gaps: list[CoverageGap] = Field(default_factory=list)


class ExtractedEntity(BaseModel):
    kind: str
    value: str


class QueryResponse(BaseModel):
    question: str
    answer: str
    troubleshooting_path: list[str] = Field(default_factory=list)
    sections: list[AnswerSection] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    related_documents: list[DocRef] = Field(default_factory=list)
    entities: list[ExtractedEntity] = Field(default_factory=list)
    intent: QueryIntentSummary | None = None
    coverage: CoverageReport | None = None
    confidence: ConfidenceReport
    followups: list[str] = Field(default_factory=list)
    latency_ms: int = 0


