"""Discrepancy / job record schemas.

A *job* is the shop's memory of a maintenance event: an aircraft had a
problem, a technician worked it, parts were swapped, a corrective action
was recorded, and the aircraft was returned to service. Each job is both
a first-class record (you can open it, read it, print it) AND a source
document for retrieval: it lands in the vector store under
``source_family="HISTORY"`` so the query engine can answer "have we
seen this before?" straight from the federation.

Design notes:

- Jobs are created from the UI via ``POST /api/jobs``. There is no
  update path in Phase 4 — once recorded, a job is history.
- The job is serialized into a small text document and run through the
  standard ingestion pipeline with ``declared_type="DISCREPANCY"`` so
  the source-family taxonomy maps it to HISTORY automatically.
- A dedicated ``JobStore`` keeps a structured copy so the History page
  can render tables, filter by aircraft/ATA, and link back to the
  underlying document record in the library.
- The same document id is used for both the vector-store chunks and the
  job record, so citations and job links can round-trip without a
  second lookup.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class JobCreateRequest(BaseModel):
    """Request body for ``POST /api/jobs``."""

    aircraft: str = Field(min_length=1, max_length=128)
    tail_number: str | None = Field(default=None, max_length=32)
    discrepancy: str = Field(min_length=5, max_length=2000)
    ata: str | None = Field(default=None, max_length=16)
    symptoms: str | None = Field(default=None, max_length=4000)
    actions_taken: str | None = Field(default=None, max_length=4000)
    parts_replaced: list[str] = Field(default_factory=list)
    corrective_action: str | None = Field(default=None, max_length=4000)
    technician: str | None = Field(default=None, max_length=128)
    technician_notes: str | None = Field(default=None, max_length=4000)
    work_order: str | None = Field(default=None, max_length=64)
    occurred_on: datetime | None = None
    status: str = Field(default="closed", pattern="^(open|in_progress|closed)$")


class JobSummary(BaseModel):
    """Short shape used by list endpoints and the History table."""

    id: str
    aircraft: str
    tail_number: str | None = None
    discrepancy: str
    ata: str | None = None
    status: str = "closed"
    technician: str | None = None
    work_order: str | None = None
    occurred_on: datetime | None = None
    created_at: datetime


class JobRecord(JobSummary):
    """Full shape returned by ``GET /api/jobs/{id}``."""

    symptoms: str | None = None
    actions_taken: str | None = None
    parts_replaced: list[str] = Field(default_factory=list)
    corrective_action: str | None = None
    technician_notes: str | None = None
    document_id: str
    chunk_count: int = 0
    indexed: bool = True


class JobListResponse(BaseModel):
    jobs: list[JobSummary] = Field(default_factory=list)
    total: int = 0


class PriorSimilarJob(BaseModel):
    """A ranked pointer back to a prior job that matches the current query.

    The query workspace uses this to power the "seen before" panel —
    a list of job ids, how strong the match is, and enough metadata to
    show a one-line card in the UI without a second round-trip.
    """

    id: str
    document_id: str
    aircraft: str
    tail_number: str | None = None
    discrepancy: str
    ata: str | None = None
    status: str = "closed"
    technician: str | None = None
    occurred_on: datetime | None = None
    score: float = 0.0
    snippet: str | None = None
    corrective_action: str | None = None


def job_document_text(payload: dict[str, Any]) -> str:
    """Render a job record as a small text document for ingestion.

    The field extractor and chunker are happy with any plain text, so we
    lay the fields out in a stable, greppable order. Keeping the tail
    number, aircraft, and ATA on their own lines makes sure the regexes
    in ``FieldExtractor`` recover them.
    """
    lines: list[str] = ["DISCREPANCY / JOB RECORD"]
    if payload.get("work_order"):
        lines.append(f"WORK ORDER: {payload['work_order']}")
    lines.append(f"AIRCRAFT: {payload.get('aircraft', '')}")
    if payload.get("tail_number"):
        lines.append(f"TAIL: {payload['tail_number']}")
    if payload.get("ata"):
        lines.append(f"ATA {payload['ata']}")
    if payload.get("occurred_on"):
        lines.append(f"DATE: {payload['occurred_on']}")
    if payload.get("technician"):
        lines.append(f"TECHNICIAN: {payload['technician']}")
    lines.append("")
    lines.append("DISCREPANCY:")
    lines.append(payload.get("discrepancy", ""))
    if payload.get("symptoms"):
        lines.append("")
        lines.append("SYMPTOMS:")
        lines.append(payload["symptoms"])
    if payload.get("actions_taken"):
        lines.append("")
        lines.append("ACTIONS TAKEN:")
        lines.append(payload["actions_taken"])
    if payload.get("parts_replaced"):
        lines.append("")
        lines.append("PARTS REPLACED:")
        for p in payload["parts_replaced"]:
            lines.append(f"- {p}")
    if payload.get("corrective_action"):
        lines.append("")
        lines.append("CORRECTIVE ACTION:")
        lines.append(payload["corrective_action"])
    if payload.get("technician_notes"):
        lines.append("")
        lines.append("TECHNICIAN NOTES:")
        lines.append(payload["technician_notes"])
    return "\n".join(lines)
