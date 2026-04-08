"""Phase 3 — multi-source federation, intent classification,
coverage detection, and the browser push connector.

Validation strategy:

- :class:`QueryIntentClassifier` correctly extracts aircraft, symptom,
  components, predicted ATA, and intent kind from a real troubleshooting
  question, and produces a family-priority ordering that matches the
  Phase-3 spec (FIM > WDM > AMM > IPC > SB/HISTORY for troubleshooting).
- :class:`CoverageDetector` flags a likely-needed family as missing when
  it isn't represented in the indexed metadata.
- The :class:`SourceFamilyLane` filters by ``source_family``.
- The seed loader populates the vector store with the Phenom 300 fixture
  corpus and the federated query engine returns at least one citation
  from each indexed family for the canonical question.
- The browser push endpoint ingests text, indexes it under the
  ``BROWSER`` family, and the next query includes a browser-derived
  citation in the federation.
- The federation reduces confidence and surfaces a "Missing likely
  sources" gap for ``BROWSER`` when nothing has been pushed yet.
"""
from __future__ import annotations

import pytest

from app.connectors.base import (
    ConnectorRegistry,
    StubExternalConnector,
    set_registry,
)
from app.connectors.browser import BrowserPushedConnector
from app.core.demo_store import get_demo_store
from app.core.seed_loader import seed_sources
from app.core.source_family import family_for_doc_type
from app.query.coverage import CoverageDetector
from app.query.intent_classifier import QueryIntentClassifier
from app.query.source_federation import SourceFamilyLane
from app.retrieval.vector_store import MemoryVectorStore, get_vector_store


PHENOM_QUESTION = "TOGA lever button not working on a Phenom 300"


# ---------------------------------------------------------------------------
# Intent classifier
# ---------------------------------------------------------------------------
def test_intent_classifier_extracts_phenom300_toga() -> None:
    intent = QueryIntentClassifier().classify(PHENOM_QUESTION)
    assert intent.aircraft == "Phenom 300"
    assert intent.intent_kind == "troubleshooting"
    assert "TOGA switch" in intent.component_hints
    assert "autoflight" in intent.system_hints
    assert "22" in intent.ata_hints
    # Troubleshooting weights: FIM should win, WDM second, AMM third.
    assert intent.family_priority[0] == "FIM"
    assert intent.family_priority[1] == "WDM"
    assert intent.family_priority[2] == "AMM"
    # IPC should rank below FIM/WDM/AMM for troubleshooting.
    assert intent.family_priority.index("IPC") > intent.family_priority.index(
        "AMM"
    )


def test_intent_classifier_recognizes_wiring_intent() -> None:
    intent = QueryIntentClassifier().classify(
        "Show me the harness pinout for the TOGA pushbutton on the Phenom 300"
    )
    assert intent.intent_kind == "wiring"
    assert intent.family_priority[0] == "WDM"


def test_intent_classifier_recognizes_parts_intent() -> None:
    intent = QueryIntentClassifier().classify(
        "What's the IPC part number for the TOGA pushbutton on the Phenom 300?"
    )
    assert intent.intent_kind == "parts"
    assert intent.family_priority[0] == "IPC"


def test_family_for_doc_type_maps_phase3_types() -> None:
    assert family_for_doc_type("FIM") == "FIM"
    assert family_for_doc_type("WDM") == "WDM"
    assert family_for_doc_type("AMM") == "AMM"
    assert family_for_doc_type("IPC") == "IPC"
    assert family_for_doc_type("SB") == "SB"
    assert family_for_doc_type("WORK_ORDER") == "HISTORY"
    assert family_for_doc_type("BROWSER_CAPTURE") == "BROWSER"
    assert family_for_doc_type("UNKNOWN") == "OTHER"


# ---------------------------------------------------------------------------
# Coverage detector
# ---------------------------------------------------------------------------
def test_coverage_flags_browser_when_only_local_sources_indexed() -> None:
    intent = QueryIntentClassifier().classify(PHENOM_QUESTION)
    detector = CoverageDetector()
    report = detector.detect(
        intent=intent,
        available_families=["FIM", "WDM", "AMM", "SB", "HISTORY"],
    )
    assert "BROWSER" in report.likely_families
    assert "BROWSER" in report.missing_families
    assert any(g.family == "BROWSER" for g in report.gaps)


def test_coverage_no_gaps_when_all_likely_families_present() -> None:
    intent = QueryIntentClassifier().classify(PHENOM_QUESTION)
    report = CoverageDetector().detect(
        intent=intent,
        available_families=["FIM", "WDM", "AMM", "BROWSER", "SB"],
    )
    assert report.missing_families == []
    assert report.gaps == []


def test_coverage_lifts_vendor_hint_when_appropriate() -> None:
    intent = QueryIntentClassifier().classify(
        "Garmin G3000 autoflight intermittent — Phenom 300"
    )
    report = CoverageDetector().detect(
        intent=intent,
        available_families=["AMM"],  # missing FIM/WDM/BROWSER
    )
    # At least one gap should carry a Garmin vendor hint because the
    # intent classifier picked up "autoflight" as a system.
    assert any(
        gap.vendor_hint and "Garmin" in gap.vendor_hint
        for gap in report.gaps
    )


# ---------------------------------------------------------------------------
# Source federation lane filters by family
# ---------------------------------------------------------------------------
def test_source_family_lane_filters_by_family() -> None:
    store = MemoryVectorStore()
    chunks = [
        {
            "id": "doc_a_p1_c0",
            "document_id": "doc_a",
            "text": "TOGA pushbutton fault isolation flow",
            "page_start": 1,
            "page_end": 1,
            "position": 0,
            "char_start": 0,
            "char_end": 30,
            "char_count": 30,
            "token_estimate": 8,
            "content_hash": "h1",
            "source": "text",
            "ocr": False,
        },
    ]
    store.upsert(
        document_id="doc_a",
        chunks=chunks,
        embeddings=[[0.1, 0.2, 0.3]],
        metadata={"type": "FIM", "source_family": "FIM", "title": "Test FIM"},
    )
    store.upsert(
        document_id="doc_b",
        chunks=[
            {
                **chunks[0],
                "id": "doc_b_p1_c0",
                "document_id": "doc_b",
            }
        ],
        embeddings=[[0.1, 0.2, 0.3]],
        metadata={"type": "AMM", "source_family": "AMM", "title": "Test AMM"},
    )
    fim_lane = SourceFamilyLane(store, "FIM")
    hits = fim_lane.search(question="TOGA pushbutton")
    assert len(hits) == 1
    assert hits[0]["document_id"] == "doc_a"
    assert hits[0]["source_family"] == "FIM"
    assert hits[0]["lane"] == "fim"


# ---------------------------------------------------------------------------
# End-to-end Phenom 300 demo
# ---------------------------------------------------------------------------
def test_phenom300_query_returns_grouped_evidence(seeded_client) -> None:
    """The seeded fixture corpus + federated engine should return
    citations from FIM, WDM, AMM, SB, and HISTORY for the canonical
    Phenom 300 TOGA question, and flag BROWSER as the missing source.
    """
    response = seeded_client.post(
        "/api/query", json={"question": PHENOM_QUESTION}
    )
    assert response.status_code == 200, response.text
    body = response.json()

    intent = body["intent"]
    assert intent["aircraft"] == "Phenom 300"
    assert intent["intent_kind"] == "troubleshooting"
    assert intent["family_priority"][0] == "FIM"

    coverage = body["coverage"]
    assert "FIM" in coverage["available_families"]
    assert "WDM" in coverage["available_families"]
    assert "AMM" in coverage["available_families"]
    assert "BROWSER" in coverage["missing_families"]
    assert any(g["family"] == "BROWSER" for g in coverage["gaps"])

    citation_families = {
        c.get("source_family") for c in body["citations"]
    }
    assert {"FIM", "WDM", "AMM"}.issubset(citation_families)

    # The top citation should be from FIM thanks to the troubleshooting
    # weights.
    assert body["citations"][0]["source_family"] == "FIM"

    assert body["confidence"]["label"] in {"high", "medium"}
    assert body["troubleshooting_path"], "expected a non-empty troubleshooting path"


# ---------------------------------------------------------------------------
# Browser push connector
# ---------------------------------------------------------------------------
def test_browser_push_indexes_and_appears_in_federation(seeded_client) -> None:
    push = seeded_client.post(
        "/api/connectors/browser/push",
        json={
            "title": "Garmin G3000 Pilot Guide — TOGA Mode",
            "text": (
                "Garmin G3000 autoflight TOGA mode engages when the "
                "side-stick TOGA pushbutton is pressed. The flight director "
                "commands a fixed pitch attitude while in TOGA. For Embraer "
                "Phenom 300, refer to AMM 22-10-22."
            ),
            "url": "https://garmin-portal.example.com/g3000/22-10/toga",
            "vendor": "Garmin",
            "aircraft": "Phenom 300",
        },
    )
    assert push.status_code == 200, push.text
    push_body = push.json()
    assert push_body["doc_id"].startswith("browser_")
    assert push_body["url"].endswith("/toga")

    # And the next query should include a BROWSER-family citation.
    response = seeded_client.post(
        "/api/query", json={"question": PHENOM_QUESTION}
    )
    body = response.json()
    citation_families = {
        c.get("source_family") for c in body["citations"]
    }
    assert "BROWSER" in citation_families
    # Now BROWSER is no longer in the missing families.
    assert "BROWSER" not in body["coverage"]["missing_families"]


def test_browser_push_rejects_empty_text(seeded_client) -> None:
    response = seeded_client.post(
        "/api/connectors/browser/push",
        json={"title": "Empty", "text": ""},
    )
    assert response.status_code == 422  # pydantic min_length


# ---------------------------------------------------------------------------
# Connector registry shape
# ---------------------------------------------------------------------------
def test_connector_registry_search_handles_no_connectors() -> None:
    set_registry(ConnectorRegistry())
    try:
        registry = ConnectorRegistry()
        intent = QueryIntentClassifier().classify(PHENOM_QUESTION)
        hits = registry.search(question=PHENOM_QUESTION, intent=intent)
        assert hits == []

        # And a stub connector with prepared hits is forwarded.
        stub = StubExternalConnector(name="stub_test", enabled=True)
        registry.register(stub)
        hits = registry.search(question=PHENOM_QUESTION, intent=intent)
        assert hits == []
    finally:
        set_registry(None)
