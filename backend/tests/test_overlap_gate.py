"""Tests for the overlap gate and the honest-refusal behavior that
depends on it.

The stub embedder hashes tokens into buckets, so completely unrelated
inputs can still yield a small non-zero cosine similarity. Without a
content-overlap gate that leak made nonsense questions look confident.
These tests lock in both the helper and the end-to-end query behavior.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.retrieval.overlap_gate import (
    apply_overlap_gate,
    content_tokens,
    has_overlap,
)


def test_content_tokens_drops_stopwords_and_short_words():
    assert content_tokens("the TOGA lever button on a Phenom 300") == {
        "toga",
        "lever",
        "button",
        "phenom",
        "300",
    }


def test_has_overlap_uses_snippet_title_and_metadata():
    question_tokens = {"toga", "phenom"}
    chunk = {
        "snippet": "Procedure for autoflight calibration.",
        "document_title": "TOGA pushbutton — Phenom 300",
    }
    assert has_overlap(question_tokens, chunk)


def test_has_overlap_returns_false_for_unrelated_content():
    question_tokens = {"pizza", "topping", "tuesday"}
    chunk = {
        "snippet": "Bleed air overtemp fault isolation step 3.",
        "document_title": "King Air 350 AMM Ch. 36",
    }
    assert not has_overlap(question_tokens, chunk)


def test_apply_overlap_gate_drops_unrelated_hits_keeps_related():
    hits = [
        {"snippet": "TOGA switch wiring for Phenom 300", "document_title": "FIM 22-10"},
        {"snippet": "Hydraulic reservoir refill", "document_title": "Citation XLS AMM"},
    ]
    kept = apply_overlap_gate("TOGA button Phenom", hits)
    assert len(kept) == 1
    assert "TOGA" in kept[0]["snippet"]


def test_apply_overlap_gate_passthrough_when_question_is_empty():
    hits = [{"snippet": "x", "document_title": "y"}]
    assert apply_overlap_gate("the", hits) == hits


def test_nonsense_question_refuses_through_api(seeded_client: TestClient):
    client = seeded_client
    resp = client.post(
        "/api/query",
        json={"question": "what is the best pizza topping for a tuesday"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["confidence"]["label"] == "insufficient"
    assert data["citations"] == []
    # The answer must not claim to have found evidence.
    assert "could not find evidence" in data["answer"].lower()


def test_toga_phenom_question_still_answers_through_api(seeded_client: TestClient):
    client = seeded_client
    resp = client.post(
        "/api/query",
        json={"question": "TOGA lever button not working on a Phenom 300"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["confidence"]["label"] in {"medium", "high"}
    # Federation must still surface multiple families for the canonical
    # troubleshooting example so the grouped sections stay populated.
    families = {c.get("source_family") for c in data["citations"]}
    assert {"FIM"} <= families
    assert len(families) >= 3
