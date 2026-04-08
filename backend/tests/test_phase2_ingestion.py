"""Phase 2 — real ingestion + retrieval coverage.

These tests focus on the behavior that must hold for Topgun AI to keep
its grounding promise:

- a real PDF gets parsed page-by-page with PyMuPDF
- chunks carry stable provenance (page, char span, content hash, source)
- the OCR stage degrades cleanly when no scanned page is present
- the vector store can list chunks for a document and answer
  similarity queries
- the document service returns chunk previews and an ingestion report
- the upload endpoint surfaces all of the above end-to-end
- the answer formatter correctly downgrades weak evidence
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ingestion.chunker import Chunker
from app.ingestion.pdf_parser import PdfParser
from app.ingestion.pipeline import IngestionContext, IngestionPipeline
from app.query.answer_formatter import AnswerFormatter, FormatterConfig
from app.retrieval.vector_store import MemoryVectorStore, get_vector_store


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _make_pdf(path: Path, pages: list[str]) -> None:
    """Build a tiny multi-page PDF on disk using PyMuPDF."""
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    for body in pages:
        page = doc.new_page()
        page.insert_text((72, 72), body)
    doc.save(str(path))
    doc.close()


# ---------------------------------------------------------------------------
# parser + chunker provenance
# ---------------------------------------------------------------------------
def test_pdf_parser_extracts_pages_with_pymupdf(tmp_path: Path) -> None:
    pytest.importorskip("fitz")
    src = tmp_path / "amm.pdf"
    _make_pdf(
        src,
        [
            "Aircraft Maintenance Manual Chapter 29 Hydraulic Power. Tail N123XL ATA 29.",
            "Pump case drain flow shall be measured with reservoir full to upper line.",
        ],
    )

    ctx = IngestionContext(doc_id="doc_pdf_test", source_path=src, title="Test PDF")
    PdfParser().run(ctx)

    assert len(ctx.pages) == 2
    assert all(p.strip() for p in ctx.pages)
    assert ctx.extracted_fields["parser_backend"] == "pymupdf"
    assert all(info["source"] == "pymupdf" for info in ctx.page_extractions)
    assert all(info["needs_ocr"] is False for info in ctx.page_extractions)


def test_chunker_carries_provenance(tmp_path: Path) -> None:
    src = tmp_path / "fixture.txt"
    src.write_text("ATA 29 hydraulic system. " * 200)

    ctx = IngestionContext(doc_id="doc_chunker", source_path=src, title="Fixture")
    PdfParser().run(ctx)
    Chunker().run(ctx)

    assert ctx.chunks
    first = ctx.chunks[0]
    expected_keys = {
        "id",
        "document_id",
        "page_start",
        "page_end",
        "position",
        "char_start",
        "char_end",
        "char_count",
        "token_estimate",
        "content_hash",
        "text",
        "source",
        "ocr",
    }
    assert expected_keys.issubset(first.keys())
    assert first["char_end"] > first["char_start"]
    assert first["content_hash"]
    assert first["source"] == "text"
    assert first["ocr"] is False


# ---------------------------------------------------------------------------
# pipeline behavior
# ---------------------------------------------------------------------------
def test_pipeline_real_pdf_indexes_chunks(tmp_path: Path) -> None:
    pytest.importorskip("fitz")
    src = tmp_path / "amm_real.pdf"
    _make_pdf(
        src,
        [
            "Aircraft Maintenance Manual hydraulic power chapter. Tail N777AA ATA 29.",
            "Hydraulic pump case drain flow shall be checked at every 100 hour inspection.",
        ],
    )

    pipeline = IngestionPipeline.default()
    result = pipeline.run(
        doc_id="doc_real_pdf",
        source_path=src,
        title="Real PDF AMM",
    )

    assert result.indexed is True
    assert result.parser_backend == "pymupdf"
    assert result.page_count == 2
    assert result.chunk_count >= 1
    assert result.ocr_applied is False
    assert "N777AA" in result.extracted_fields.get("tail_numbers", [])

    # And the vector store can find that document.
    store = get_vector_store()
    chunks = store.list_chunks("doc_real_pdf")
    assert chunks
    assert all(c.source == "pymupdf" for c in chunks)


def test_pipeline_marks_failed_status_on_missing_source(tmp_path: Path) -> None:
    pipeline = IngestionPipeline.default()
    result = pipeline.run(
        doc_id="doc_missing",
        source_path=tmp_path / "does_not_exist.pdf",
        title="Missing",
    )
    assert result.indexed is False
    assert result.error is not None
    assert "pdf_parser" in result.error


def test_ocr_stage_skips_cleanly_when_pages_have_text(tmp_path: Path) -> None:
    pytest.importorskip("fitz")
    src = tmp_path / "good.pdf"
    _make_pdf(src, ["Plenty of usable text on this page for the parser."])

    pipeline = IngestionPipeline.default()
    result = pipeline.run(doc_id="doc_no_ocr", source_path=src, title="No OCR")
    assert result.ocr_applied is False
    assert result.ocr_pages == []


# ---------------------------------------------------------------------------
# vector store + retrieval
# ---------------------------------------------------------------------------
def test_vector_store_list_and_count() -> None:
    store = MemoryVectorStore()
    store.upsert(
        document_id="docX",
        chunks=[
            {
                "id": "docX_p1_c0",
                "document_id": "docX",
                "text": "hydraulic pressure fluctuation note",
                "page_start": 1,
                "page_end": 1,
                "position": 0,
                "char_start": 0,
                "char_end": 32,
                "char_count": 32,
                "token_estimate": 8,
                "content_hash": "abc",
                "source": "pymupdf",
                "ocr": False,
            },
            {
                "id": "docX_p1_c1",
                "document_id": "docX",
                "text": "second chunk same page",
                "page_start": 1,
                "page_end": 1,
                "position": 1,
                "char_start": 32,
                "char_end": 60,
                "char_count": 28,
                "token_estimate": 7,
                "content_hash": "def",
                "source": "pymupdf",
                "ocr": False,
            },
        ],
        embeddings=[[0.1, 0.2, 0.3], [0.05, 0.1, 0.2]],
        metadata={"type": "AMM", "title": "Test AMM"},
    )

    listed = store.list_chunks("docX")
    assert len(listed) == 2
    assert store.chunk_count("docX") == 2
    assert listed[0].position == 0  # ordering is page,position
    removed = store.delete_document("docX")
    assert removed == 2
    assert store.chunk_count("docX") == 0


# ---------------------------------------------------------------------------
# document service / detail endpoint
# ---------------------------------------------------------------------------
def test_upload_returns_ingestion_report_and_previews(client: TestClient) -> None:
    payload = (
        "Aircraft Maintenance Manual — Chapter 29 Hydraulic Power\n"
        "Tail: N555ZA ATA 29\n"
        "Pump case drain flow shall be measured with reservoir full.\n"
        "Bulletin SB-29-04 supersedes earlier inspection interval."
    )
    files = {
        "file": ("phase2.txt", io.BytesIO(payload.encode("utf-8")), "text/plain"),
    }
    response = client.post(
        "/api/documents/upload",
        files=files,
        data={"title": "Phase2 AMM", "type": "UNKNOWN"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "indexed"
    assert body["type"] == "AMM"
    assert body["ingestion"]["chunk_count"] >= 1
    assert body["ingestion"]["indexed"] is True
    assert body["ingestion"]["ocr_applied"] is False
    assert body["chunk_previews"], "expected at least one chunk preview"
    preview = body["chunk_previews"][0]
    assert preview["snippet"]
    assert preview["page_start"] == 1
    assert preview["source"] == "text"

    # And the detail endpoint returns the same shape.
    detail = client.get(f"/api/documents/{body['id']}")
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["id"] == body["id"]
    assert detail_body["chunk_previews"]
    assert detail_body["ingestion"]["chunk_count"] >= 1


# ---------------------------------------------------------------------------
# answer formatter — weak / insufficient handling
# ---------------------------------------------------------------------------
def test_formatter_marks_weak_evidence_as_low() -> None:
    formatter = AnswerFormatter(FormatterConfig(weak_score_floor=0.5))
    result = formatter.format(
        question="anything",
        chunks=[
            {
                "id": "c1",
                "document_id": "doc1",
                "document_title": "Sample AMM",
                "document_type": "AMM",
                "page": 7,
                "snippet": "Pump case drain flow limits listed below.",
                "score": 0.2,
                "source": "pymupdf",
                "ocr": False,
            }
        ],
    )
    assert result["confidence"]["label"] == "low"
    assert "weak" in result["confidence"]["reason"].lower()
    assert "verify" in result["answer"].lower()


def test_formatter_refuses_below_insufficient_floor() -> None:
    formatter = AnswerFormatter(
        FormatterConfig(insufficient_score_floor=0.99, weak_score_floor=0.99)
    )
    result = formatter.format(
        question="anything",
        chunks=[
            {
                "id": "c1",
                "document_id": "doc1",
                "document_title": "Sample AMM",
                "document_type": "AMM",
                "page": 1,
                "snippet": "irrelevant",
                "score": 0.01,
            }
        ],
    )
    assert result["confidence"]["label"] == "insufficient"
    assert result["related_documents"] == []
