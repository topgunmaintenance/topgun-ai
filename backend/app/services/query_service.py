"""Business logic for the query workspace."""
from __future__ import annotations

import time
from typing import Any

from app.core.demo_store import DemoStore, get_demo_store
from app.query.query_engine import QueryEngine
from app.schemas.common import ConfidenceReport, DocRef
from app.schemas.jobs import PriorSimilarJob
from app.schemas.query import (
    AnswerSection,
    Citation,
    CoverageReport,
    ExtractedEntity,
    QueryIntentSummary,
    QueryRequest,
    QueryResponse,
)
from app.services.job_service import JobService, get_job_service


class QueryService:
    def __init__(
        self,
        store: DemoStore,
        engine: QueryEngine,
        *,
        job_service: JobService,
    ) -> None:
        self._store = store
        self._engine = engine
        self._job_service = job_service

    # ------------------------------------------------------------------
    def ask(self, request: QueryRequest) -> QueryResponse:
        start = time.perf_counter()
        result = self._engine.handle(request)

        prior_similar_jobs = [
            PriorSimilarJob(**j)
            for j in self._job_service.find_similar(
                question=request.question, top_k=4
            )
        ]

        latency_ms = int((time.perf_counter() - start) * 1000)

        return QueryResponse(
            question=request.question,
            answer=result["answer"],
            troubleshooting_path=list(result.get("troubleshooting_path", [])),
            sections=[AnswerSection(**s) for s in result.get("sections", [])],
            citations=[
                Citation(**c)
                for c in result.get("citations", [])[: request.max_citations]
            ],
            related_documents=[DocRef(**d) for d in result.get("related_documents", [])],
            entities=[ExtractedEntity(**e) for e in result.get("entities", [])],
            intent=(
                QueryIntentSummary(**result["intent"]) if result.get("intent") else None
            ),
            coverage=(
                CoverageReport(**result["coverage"]) if result.get("coverage") else None
            ),
            confidence=ConfidenceReport(**result["confidence"]),
            followups=list(result.get("followups", [])),
            prior_similar_jobs=prior_similar_jobs,
            latency_ms=latency_ms,
        )

    # ------------------------------------------------------------------
    def recent(self, *, limit: int) -> list[dict[str, Any]]:
        records = self._store.list_recent_queries(limit=limit)
        return [
            {
                "id": r["id"],
                "question": r["question"],
                "created_at": r.get("created_at"),
                "confidence": r.get("confidence", {}).get("label", "medium"),
            }
            for r in records
        ]


# ---------------------------------------------------------------------------
def get_query_service() -> QueryService:
    store = get_demo_store()
    return QueryService(
        store=store,
        engine=QueryEngine.default(store),
        job_service=get_job_service(),
    )
