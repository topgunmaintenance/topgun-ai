"""Discrepancy / job record endpoints.

Thin FastAPI router wired on top of :class:`app.services.job_service.JobService`.

Endpoints
---------

- ``POST /api/jobs`` — create a new discrepancy / job record. The job
  is persisted in the JobStore, indexed into the vector store as a
  ``HISTORY`` family document, and mirrored into the Document Library.
- ``GET  /api/jobs`` — list jobs with optional filters (aircraft,
  tail_number, ata, status).
- ``GET  /api/jobs/{job_id}`` — full record for the History detail page.

The router deliberately returns the same ``JobSummary`` /
``JobRecord`` shapes the frontend types expect, so the frontend
client is a tiny one-to-one wrapper.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.jobs import (
    JobCreateRequest,
    JobListResponse,
    JobRecord,
    JobSummary,
)
from app.services.job_service import JobService, get_job_service

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _to_summary(record: dict[str, Any]) -> JobSummary:
    return JobSummary(
        id=record["id"],
        aircraft=record["aircraft"],
        tail_number=record.get("tail_number"),
        discrepancy=record["discrepancy"],
        ata=record.get("ata"),
        status=record.get("status", "closed"),
        technician=record.get("technician"),
        work_order=record.get("work_order"),
        occurred_on=_as_datetime(record.get("occurred_on")),
        created_at=_as_datetime(record.get("created_at")) or datetime.utcnow(),
    )


def _to_record(record: dict[str, Any]) -> JobRecord:
    return JobRecord(
        id=record["id"],
        aircraft=record["aircraft"],
        tail_number=record.get("tail_number"),
        discrepancy=record["discrepancy"],
        ata=record.get("ata"),
        status=record.get("status", "closed"),
        technician=record.get("technician"),
        work_order=record.get("work_order"),
        occurred_on=_as_datetime(record.get("occurred_on")),
        created_at=_as_datetime(record.get("created_at")) or datetime.utcnow(),
        symptoms=record.get("symptoms"),
        actions_taken=record.get("actions_taken"),
        parts_replaced=list(record.get("parts_replaced") or []),
        corrective_action=record.get("corrective_action"),
        technician_notes=record.get("technician_notes"),
        document_id=record["document_id"],
        chunk_count=int(record.get("chunk_count") or 0),
        indexed=bool(record.get("indexed", True)),
    )


def _as_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


@router.post(
    "",
    response_model=JobRecord,
    status_code=status.HTTP_201_CREATED,
)
def create_job(
    request: JobCreateRequest,
    service: JobService = Depends(get_job_service),
) -> JobRecord:
    try:
        record = service.create(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _to_record(record)


@router.get("", response_model=JobListResponse)
def list_jobs(
    aircraft: str | None = None,
    tail_number: str | None = None,
    ata: str | None = None,
    status: str | None = None,
    service: JobService = Depends(get_job_service),
) -> JobListResponse:
    items = service.list(
        aircraft=aircraft,
        tail_number=tail_number,
        ata=ata,
        status=status,
    )
    return JobListResponse(
        jobs=[_to_summary(r) for r in items],
        total=len(items),
    )


@router.get("/{job_id}", response_model=JobRecord)
def get_job(
    job_id: str,
    service: JobService = Depends(get_job_service),
) -> JobRecord:
    record = service.get(job_id)
    if not record:
        raise HTTPException(status_code=404, detail="job not found")
    return _to_record(record)
