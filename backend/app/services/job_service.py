"""Business logic for discrepancy / job records.

This service is the bridge between the ``/api/jobs`` endpoints, the
in-memory ``JobStore``, and the ingestion + vector-store plumbing that
turns every job into a first-class HISTORY document.

Responsibilities:

1. **Create** — accept a structured job payload, render it as a small
   text document, run it through the standard ingestion pipeline with
   ``declared_type="DISCREPANCY"`` (which maps to ``source_family="HISTORY"``),
   patch the chunk metadata with job-specific fields (tail, ATA,
   technician), and persist the structured record.
2. **Read** — list and fetch job records for the History page.
3. **Retrieve similar** — given a question, run a HISTORY-only
   similarity search, apply the content-overlap gate (so the stub
   embedder can't leak false positives), and shape the top hits into
   ``PriorSimilarJob`` records. This feeds the "seen before" panel in
   the Query Workspace.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.demo_store import DemoStore, get_demo_store
from app.core.job_store import JobStore, get_job_store, utcnow
from app.core.logging import get_logger
from app.ingestion.pipeline import IngestionPipeline, IngestionResult
from app.retrieval.overlap_gate import apply_overlap_gate
from app.retrieval.vector_store import VectorStore, get_vector_store
from app.schemas.jobs import JobCreateRequest, job_document_text
from app.services.ai_provider import get_ai_provider
from app.utils.text import normalize_whitespace, truncate

log = get_logger(__name__)


class JobService:
    def __init__(
        self,
        *,
        store: JobStore,
        demo_store: DemoStore,
        pipeline: IngestionPipeline,
        vector_store: VectorStore,
        upload_dir: Path,
    ) -> None:
        self._store = store
        self._demo_store = demo_store
        self._pipeline = pipeline
        self._vector_store = vector_store
        self._upload_dir = upload_dir

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------
    def create(self, request: JobCreateRequest) -> dict[str, Any]:
        """Record a new job and index it into the vector store."""

        payload = request.model_dump(exclude_none=False)
        # occurred_on / created_at normalization.
        occurred_on = request.occurred_on or utcnow()
        payload["occurred_on"] = occurred_on.isoformat()
        created_at = utcnow()

        text = job_document_text(
            {**payload, "occurred_on": occurred_on.date().isoformat()}
        )
        if not text.strip():
            raise ValueError("job payload renders to an empty document")

        digest = hashlib.sha256(
            f"{request.aircraft}|{request.discrepancy}|{created_at.isoformat()}".encode(
                "utf-8"
            )
        ).hexdigest()[:16]
        job_id = f"job_{digest}"
        doc_id = f"doc_{job_id}"

        self._upload_dir.mkdir(parents=True, exist_ok=True)
        path = self._upload_dir / f"{doc_id}.txt"
        path.write_text(text)

        title = _title_for(request)
        result: IngestionResult = self._pipeline.run(
            doc_id=doc_id,
            source_path=path,
            title=title,
            doc_type="DISCREPANCY",
            aircraft=request.aircraft,
            source="job_record",
        )

        self._patch_metadata(
            doc_id=doc_id,
            job_id=job_id,
            request=request,
            occurred_on=occurred_on,
            title=title,
        )

        record: dict[str, Any] = {
            "id": job_id,
            "document_id": doc_id,
            "aircraft": request.aircraft,
            "tail_number": request.tail_number,
            "discrepancy": request.discrepancy,
            "ata": request.ata,
            "symptoms": request.symptoms,
            "actions_taken": request.actions_taken,
            "parts_replaced": list(request.parts_replaced),
            "corrective_action": request.corrective_action,
            "technician": request.technician,
            "technician_notes": request.technician_notes,
            "work_order": request.work_order,
            "occurred_on": occurred_on,
            "status": request.status,
            "created_at": created_at,
            "chunk_count": result.chunk_count,
            "indexed": result.indexed,
        }
        self._store.add(record)

        # Also surface the job in the Document Library so the existing
        # library flow can link to it like any other indexed doc.
        self._register_library_document(
            record=record,
            result=result,
            title=title,
        )

        return record

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------
    def list(
        self,
        *,
        aircraft: str | None = None,
        tail_number: str | None = None,
        ata: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._store.list(
            aircraft=aircraft,
            tail_number=tail_number,
            ata=ata,
            status=status,
        )

    def get(self, job_id: str) -> dict[str, Any] | None:
        return self._store.get(job_id)

    def get_by_document(self, document_id: str) -> dict[str, Any] | None:
        return self._store.get_by_document(document_id)

    def reset(self) -> None:
        """Test helper: clear structured records (chunks are separate)."""
        self._store.reset()

    # ------------------------------------------------------------------
    # Retrieve similar
    # ------------------------------------------------------------------
    def find_similar(
        self, *, question: str, top_k: int = 4
    ) -> list[dict[str, Any]]:
        """Return top matching jobs for a question.

        Runs a HISTORY-only similarity search against the vector store,
        drops hits that fail the content-overlap gate (stub-embedder
        insurance), and then joins each vector hit back onto a structured
        job record via ``document_id``. Seeded internal-history fixtures
        (work orders from ``sample_data/sources``) are *not* joined to a
        structured ``JobRecord`` — those stay visible in the normal
        "Internal History" citation section and are filtered out here so
        the "seen before" panel is always structured-job-backed.
        """
        if not question.strip():
            return []

        provider = get_ai_provider()
        [embedding] = provider.embed([question])
        raw = self._vector_store.similarity_search(
            embedding=embedding,
            top_k=top_k * 3,  # oversample — we filter twice
            source_families=["HISTORY"],
        )
        shaped = [
            {
                "document_id": chunk.document_id,
                "snippet": chunk.text[:280],
                "document_title": chunk.metadata.get("title", chunk.document_id),
                "score": float(score),
                "page": chunk.page_start,
                "ata": chunk.metadata.get("ata_chapters") or [],
                "components": chunk.metadata.get("components") or [],
                "aircraft_model": chunk.metadata.get("aircraft_model"),
            }
            for chunk, score in raw
        ]

        gated = apply_overlap_gate(question, shaped)

        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for hit in gated:
            doc_id = hit["document_id"]
            if doc_id in seen:
                continue
            seen.add(doc_id)

            job = self._store.get_by_document(doc_id)
            if not job:
                # Seeded work-order fixtures live in the vector store but
                # don't have a structured JobRecord. Leave them to the
                # normal "Internal History" citation flow.
                continue
            out.append(
                {
                    "id": job["id"],
                    "document_id": doc_id,
                    "aircraft": job["aircraft"],
                    "tail_number": job.get("tail_number"),
                    "discrepancy": job["discrepancy"],
                    "ata": job.get("ata"),
                    "status": job.get("status", "closed"),
                    "technician": job.get("technician"),
                    "occurred_on": job.get("occurred_on"),
                    "score": hit["score"],
                    "snippet": truncate(
                        normalize_whitespace(hit["snippet"]), 220
                    ),
                    "corrective_action": job.get("corrective_action"),
                }
            )
            if len(out) >= top_k:
                break
        return out

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _patch_metadata(
        self,
        *,
        doc_id: str,
        job_id: str,
        request: JobCreateRequest,
        occurred_on: datetime,
        title: str,
    ) -> None:
        chunks = self._vector_store.list_chunks(doc_id)
        if not chunks:
            return
        patch: dict[str, Any] = {
            "source_family": "HISTORY",
            "type": "DISCREPANCY",
            "title": title,
            "job_id": job_id,
            "captured_at": occurred_on.isoformat(),
        }
        if request.tail_number:
            patch["tail_number"] = request.tail_number
        if request.ata:
            # Merge ATA from the payload with anything the extractor
            # recovered, normalized to two-digit chapter strings.
            existing = list(chunks[0].metadata.get("ata_chapters") or [])
            ata = _normalize_ata(request.ata)
            if ata and ata not in existing:
                existing.insert(0, ata)
            patch["ata_chapters"] = existing
        if request.work_order:
            patch["document_code"] = f"WO-{request.work_order}"
        if request.technician:
            patch["vendor"] = request.technician  # re-used UI field
        for c in chunks:
            c.metadata.update(patch)

    def _register_library_document(
        self,
        *,
        record: dict[str, Any],
        result: IngestionResult,
        title: str,
    ) -> None:
        """Add the job as a library document so it shows up in /library."""
        doc = {
            "id": record["document_id"],
            "title": title,
            "type": "DISCREPANCY",
            "source_family": "HISTORY",
            "aircraft": record["aircraft"],
            "aircraft_model": result.extracted_fields.get("aircraft_model")
            or record["aircraft"],
            "source": "job_record",
            "url": None,
            "vendor": record.get("technician"),
            "document_code": f"WO-{record['work_order']}" if record.get("work_order") else None,
            "revision": None,
            "ata": _tags_ata(record, result),
            "components": list(result.extracted_fields.get("components") or []),
            "captured_at": record["occurred_on"].isoformat()
            if isinstance(record["occurred_on"], datetime)
            else record["occurred_on"],
            "status": "indexed" if result.indexed else "failed",
            "pages": max(result.page_count, 1),
            "size_mb": 0.01,
            "uploaded_at": record["created_at"].isoformat()
            if isinstance(record["created_at"], datetime)
            else record["created_at"],
            "uploaded_by": record.get("technician") or "job_record",
            "tags": _library_tags(record),
            "summary": record["discrepancy"][:200],
            "ingestion": {
                "parser_backend": result.parser_backend,
                "page_count": result.page_count,
                "chunk_count": result.chunk_count,
                "indexed": result.indexed,
                "ocr_applied": False,
                "ocr_pages": [],
                "extracted_fields": dict(result.extracted_fields),
                "error": result.error,
            },
            "chunk_previews": [],
        }
        self._demo_store.upsert_document(doc)


# ---------------------------------------------------------------------------
# Small pure helpers
# ---------------------------------------------------------------------------
def _title_for(request: JobCreateRequest) -> str:
    bits: list[str] = []
    if request.tail_number:
        bits.append(request.tail_number)
    elif request.aircraft:
        bits.append(request.aircraft)
    if request.ata:
        bits.append(f"ATA {request.ata}")
    bits.append(request.discrepancy[:80])
    return " · ".join(b for b in bits if b)


def _normalize_ata(raw: str) -> str | None:
    raw = raw.strip().upper()
    if not raw:
        return None
    if raw.startswith("ATA"):
        raw = raw[3:].strip()
    if raw.isdigit():
        return raw.zfill(2)[:2]
    return raw[:4]


def _tags_ata(record: dict[str, Any], result: IngestionResult) -> list[str]:
    ata: list[str] = []
    if record.get("ata"):
        normalized = _normalize_ata(record["ata"])
        if normalized:
            ata.append(normalized)
    for chapter in result.extracted_fields.get("ata_chapters", []) or []:
        if chapter not in ata:
            ata.append(chapter)
    return ata


def _library_tags(record: dict[str, Any]) -> list[str]:
    tags: list[str] = ["discrepancy", "history"]
    if record.get("tail_number"):
        tags.append(record["tail_number"])
    if record.get("ata"):
        normalized = _normalize_ata(record["ata"])
        if normalized:
            tags.append(f"ATA {normalized}")
    if record.get("work_order"):
        tags.append(f"WO {record['work_order']}")
    if record.get("status") and record["status"] != "closed":
        tags.append(record["status"])
    return tags


# ---------------------------------------------------------------------------
def get_job_service() -> JobService:
    settings = get_settings()
    return JobService(
        store=get_job_store(),
        demo_store=get_demo_store(),
        pipeline=IngestionPipeline.default(),
        vector_store=get_vector_store(),
        upload_dir=settings.upload_dir / "jobs",
    )
