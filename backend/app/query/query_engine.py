"""Federated query engine.

Phase 3 replaces the old four-lane manual/history/parts/pattern split
with a *source-family* federation: one lane per family (FIM, WDM, AMM,
IPC, SB, HISTORY, BROWSER, EXTERNAL). The flow is:

1. Classify the question into a :class:`QueryIntent` (aircraft,
   symptom, components, predicted ATA, intent kind, family weights).
2. Detect source coverage: which families are likely needed for this
   intent vs. which are actually available in the index + connectors.
3. Run a similarity search per family lane and per registered external
   connector (e.g. authorized browser-push results).
4. Merge with reciprocal-rank fusion using the intent's family weights
   so the right family wins ties.
5. Hand the merged set + intent + coverage to the answer formatter for
   grouped synthesis.
6. Return the structured response with citations, grouped sections,
   the intent summary, and the coverage report (so the UI can render
   "Missing likely sources").

The demo-store fast path is preserved (overlap-gated) so canned answers
still respond instantly to seeded questions.
"""
from __future__ import annotations

from typing import Any

from app.connectors.base import ConnectorRegistry, get_registry
from app.core.demo_store import DemoStore
from app.core.logging import get_logger
from app.core.source_family import (
    ALL_SOURCE_FAMILIES,
    SourceFamily,
    label_for,
)
from app.query.answer_formatter import AnswerFormatter
from app.query.citation_builder import build_citations
from app.query.coverage import CoverageDetector, families_from_metadata
from app.query.intent_classifier import QueryIntent, QueryIntentClassifier
from app.query.source_federation import SourceFamilyLane
from app.retrieval.overlap_gate import apply_overlap_gate
from app.retrieval.ranker import reciprocal_rank_fusion
from app.retrieval.vector_store import VectorStore, get_vector_store
from app.schemas.query import QueryRequest

log = get_logger(__name__)


# Families we always create lanes for. EXTERNAL is intentionally not
# in this list — it's served by registered connectors instead.
_LANE_FAMILIES: tuple[SourceFamily, ...] = (
    "FIM",
    "WDM",
    "AMM",
    "IPC",
    "SB",
    "HISTORY",
    "BROWSER",
    "OTHER",
)


class QueryEngine:
    def __init__(
        self,
        *,
        demo_store: DemoStore,
        vector_store: VectorStore,
        intent_classifier: QueryIntentClassifier,
        formatter: AnswerFormatter,
        coverage_detector: CoverageDetector,
        connector_registry: ConnectorRegistry,
    ) -> None:
        self._demo_store = demo_store
        self._vector_store = vector_store
        self._intent_classifier = intent_classifier
        self._formatter = formatter
        self._coverage_detector = coverage_detector
        self._connector_registry = connector_registry
        self._lanes: dict[SourceFamily, SourceFamilyLane] = {
            family: SourceFamilyLane(vector_store, family)
            for family in _LANE_FAMILIES
        }

    # ------------------------------------------------------------------
    @classmethod
    def default(cls, demo_store: DemoStore) -> "QueryEngine":
        return cls(
            demo_store=demo_store,
            vector_store=get_vector_store(),
            intent_classifier=QueryIntentClassifier(),
            formatter=AnswerFormatter(),
            coverage_detector=CoverageDetector(),
            connector_registry=get_registry(),
        )

    # ------------------------------------------------------------------
    def handle(self, request: QueryRequest) -> dict[str, Any]:
        intent = self._intent_classifier.classify(request.question)

        # 1. Demo fast path (overlap-gated). We still return the canned
        # answer when the question is essentially a seeded one — but we
        # also attach the freshly classified intent + coverage so the UI
        # can render the panels consistently.
        demo_hit = self._demo_store.find_query(request.question)
        if demo_hit:
            log.info(
                "query_engine: demo-store hit for %r", request.question[:60]
            )
            return self._from_demo(demo_hit, intent)

        # 2. Federation: one lane per family + connector fan-out.
        lane_hits = self._run_lanes(request, intent)
        connector_hits = self._run_connectors(request, intent)

        all_lanes: dict[str, list[dict[str, Any]]] = {**lane_hits}
        if connector_hits:
            all_lanes["external"] = connector_hits

        weights = self._lane_weights_from_intent(intent)
        fused = reciprocal_rank_fusion(all_lanes, weights=weights)

        # 3. Coverage: which families are likely needed but missing?
        coverage = self._coverage_detector.detect(
            intent=intent,
            available_families=self._available_families(connector_hits),
        )

        # 4. Synthesis (grouped + missing-sources aware).
        synthesized = self._formatter.format(
            question=request.question,
            chunks=fused,
            intent=intent,
            coverage=coverage,
        )
        synthesized["citations"] = build_citations(
            fused[: request.max_citations]
        )
        synthesized["intent"] = intent.to_dict()
        synthesized["coverage"] = coverage.to_dict()
        return synthesized

    # ------------------------------------------------------------------
    def _run_lanes(
        self, request: QueryRequest, intent: QueryIntent
    ) -> dict[str, list[dict[str, Any]]]:
        # If the caller explicitly restricted source families, honor it.
        allowed = set(request.source_families or []) if request.source_families else None
        out: dict[str, list[dict[str, Any]]] = {}
        for family, lane in self._lanes.items():
            if allowed and family not in allowed:
                continue
            hits = lane.search(question=request.question)
            if hits:
                out[lane.name] = hits
        return out

    def _run_connectors(
        self, request: QueryRequest, intent: QueryIntent
    ) -> list[dict[str, Any]]:
        hits = self._connector_registry.search(
            question=request.question, intent=intent
        )
        shaped = [h.to_chunk() for h in hits]
        # Connector hits come from external systems and we have no
        # embedding guarantees for them, so gate on content overlap too.
        return apply_overlap_gate(request.question, shaped)

    def _lane_weights_from_intent(
        self, intent: QueryIntent
    ) -> dict[str, float]:
        # Lane names are family names lowercased; "external" matches the
        # connector lane name we set above.
        weights: dict[str, float] = {}
        for family, weight in intent.family_weights.items():
            weights[family.lower()] = weight
        weights["external"] = intent.family_weights.get("EXTERNAL", 0.7)
        return weights

    def _available_families(
        self, connector_hits: list[dict[str, Any]]
    ) -> list[str]:
        from_index = families_from_metadata(self._vector_store.all_metadata())
        from_connectors: set[str] = set()
        for h in connector_hits:
            family = h.get("source_family")
            if family:
                from_connectors.add(family)
        return sorted(set(from_index) | from_connectors)

    # ------------------------------------------------------------------
    def _from_demo(
        self, demo_hit: dict[str, Any], intent: QueryIntent
    ) -> dict[str, Any]:
        coverage = self._coverage_detector.detect(
            intent=intent,
            available_families=self._available_families([]),
        )
        return {
            "answer": demo_hit["answer"],
            "sections": demo_hit.get("sections", []),
            "citations": demo_hit.get("citations", []),
            "related_documents": demo_hit.get("related_documents", []),
            "entities": demo_hit.get("entities", []),
            "confidence": demo_hit.get(
                "confidence",
                {
                    "score": 0.7,
                    "label": "medium",
                    "reason": "Demo store match.",
                },
            ),
            "followups": demo_hit.get("followups", []),
            "intent": intent.to_dict(),
            "coverage": coverage.to_dict(),
        }
