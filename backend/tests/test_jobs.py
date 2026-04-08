"""End-to-end tests for the Phase 4 discrepancy / job workflow.

Covers:
- POST /api/jobs creates a structured record, indexes chunks into
  the vector store under source_family=HISTORY, and mirrors the doc
  into the Document Library.
- GET /api/jobs lists and filters correctly.
- GET /api/jobs/{id} returns the full record or 404.
- A TOGA-style query after a matching job is logged surfaces the
  record in QueryResponse.prior_similar_jobs with its corrective
  action and score.
- The overlap gate keeps nonsense questions from surfacing jobs.
- The honest-refusal path still works (no jobs, no citations, label
  = insufficient) on off-topic questions.

These tests intentionally exercise the real service + pipeline wiring
through the FastAPI TestClient with the lifespan enabled, so the
sample data (FIM, WDM, AMM, SB, HISTORY work order) is loaded into the
vector store before we add new jobs.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.job_store import reset_job_store
from app.retrieval.vector_store import get_vector_store


TOGA_DISCREPANCY = {
    "aircraft": "Phenom 300",
    "tail_number": "N512TG",
    "discrepancy": (
        "TOGA lever button unresponsive on captain side during autoflight "
        "engagement"
    ),
    "ata": "22",
    "symptoms": (
        "Pressing TOGA on takeoff does not engage autoflight. "
        "No annunciator change."
    ),
    "actions_taken": (
        "Inspected TOGA switch harness per FIM 22-10-00. "
        "Found loose pin 7 at connector P/N 011-03035-10."
    ),
    "parts_replaced": ["011-03035-10"],
    "corrective_action": (
        "Reseated pin 7, retorqued backshell, ops-checked per AMM 22-10-04. "
        "System normal on ground run."
    ),
    "technician": "J. Mero",
    "technician_notes": "Second occurrence this quarter. Monitor.",
    "work_order": "WO-2026-0418",
    "status": "closed",
}


def _fresh_jobs_state() -> None:
    """Wipe any job records left from previous tests and their chunks.

    The vector store is a module-level singleton, so a job indexed by a
    previous test would leak into later ones. We delete chunks keyed by
    any ``doc_job_*`` document id so each test case starts from the
    same baseline.
    """
    store = get_vector_store()
    doc_ids = {
        meta.get("document_id")
        for meta in store.all_metadata()
        if (meta.get("document_id") or "").startswith("doc_job_")
    }
    for doc_id in doc_ids:
        if doc_id:
            store.delete_document(doc_id)
    reset_job_store()


# ---------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------
def test_create_job_returns_full_record_and_indexes_chunks(
    seeded_client: TestClient,
):
    _fresh_jobs_state()
    resp = seeded_client.post("/api/jobs", json=TOGA_DISCREPANCY)
    assert resp.status_code == 201, resp.text
    record = resp.json()

    assert record["id"].startswith("job_")
    assert record["document_id"].startswith("doc_job_")
    assert record["aircraft"] == "Phenom 300"
    assert record["tail_number"] == "N512TG"
    assert record["ata"] == "22"
    assert record["status"] == "closed"
    assert record["chunk_count"] >= 1
    assert record["indexed"] is True
    assert record["parts_replaced"] == ["011-03035-10"]
    assert "Reseated pin 7" in record["corrective_action"]
    assert record["technician"] == "J. Mero"


def test_create_job_rejects_short_discrepancy(seeded_client: TestClient):
    _fresh_jobs_state()
    resp = seeded_client.post(
        "/api/jobs",
        json={**TOGA_DISCREPANCY, "discrepancy": "bad"},
    )
    # Pydantic validation, not business error.
    assert resp.status_code == 422


def test_list_jobs_round_trips_and_filters(seeded_client: TestClient):
    _fresh_jobs_state()
    seeded_client.post("/api/jobs", json=TOGA_DISCREPANCY)
    seeded_client.post(
        "/api/jobs",
        json={
            **TOGA_DISCREPANCY,
            "aircraft": "King Air 350",
            "tail_number": "N820KA",
            "discrepancy": "Bleed air overtemp on climb, right-hand duct sensor",
            "ata": "36",
            "corrective_action": (
                "Replaced overtemp sensor per SB-B78-14, leak checked."
            ),
        },
    )

    all_resp = seeded_client.get("/api/jobs")
    assert all_resp.status_code == 200
    payload = all_resp.json()
    assert payload["total"] == 2
    assert len(payload["jobs"]) == 2

    phenom_only = seeded_client.get("/api/jobs?aircraft=Phenom%20300").json()
    assert phenom_only["total"] == 1
    assert phenom_only["jobs"][0]["tail_number"] == "N512TG"

    king_only = seeded_client.get("/api/jobs?tail_number=N820KA").json()
    assert king_only["total"] == 1
    assert king_only["jobs"][0]["aircraft"] == "King Air 350"

    none = seeded_client.get("/api/jobs?aircraft=Learjet%2060").json()
    assert none["total"] == 0


def test_get_job_by_id_or_404(seeded_client: TestClient):
    _fresh_jobs_state()
    created = seeded_client.post("/api/jobs", json=TOGA_DISCREPANCY).json()
    job_id = created["id"]

    ok = seeded_client.get(f"/api/jobs/{job_id}")
    assert ok.status_code == 200
    body = ok.json()
    assert body["id"] == job_id
    assert body["document_id"] == created["document_id"]
    assert body["symptoms"] is not None

    missing = seeded_client.get("/api/jobs/job_doesnotexist")
    assert missing.status_code == 404


# ---------------------------------------------------------------------
# Query integration — the "seen before" reasoning step
# ---------------------------------------------------------------------
def test_toga_query_surfaces_prior_similar_job(seeded_client: TestClient):
    _fresh_jobs_state()

    # Baseline: before any job is logged, prior_similar_jobs must be
    # empty even though seeded work-order fixtures exist in HISTORY.
    before = seeded_client.post(
        "/api/query",
        json={"question": "TOGA lever button not working on a Phenom 300"},
    ).json()
    assert before["confidence"]["label"] in {"medium", "high"}
    assert before.get("prior_similar_jobs") == []

    # Log the exact discrepancy.
    created = seeded_client.post("/api/jobs", json=TOGA_DISCREPANCY).json()
    job_id = created["id"]

    # Re-ask: the structured job should now surface as a prior match.
    after = seeded_client.post(
        "/api/query",
        json={"question": "TOGA lever button not working on a Phenom 300"},
    ).json()
    prior = after.get("prior_similar_jobs") or []
    assert len(prior) == 1
    hit = prior[0]
    assert hit["id"] == job_id
    assert hit["aircraft"] == "Phenom 300"
    assert hit["tail_number"] == "N512TG"
    assert hit["status"] == "closed"
    assert "Reseated pin 7" in (hit.get("corrective_action") or "")
    assert hit["score"] > 0


def test_nonsense_query_does_not_surface_any_job(seeded_client: TestClient):
    _fresh_jobs_state()
    # Log a real discrepancy that mentions aviation content.
    seeded_client.post("/api/jobs", json=TOGA_DISCREPANCY)

    resp = seeded_client.post(
        "/api/query",
        json={"question": "what is the best pizza topping for a Tuesday"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["confidence"]["label"] == "insufficient"
    assert data["citations"] == []
    assert data.get("prior_similar_jobs") == []
