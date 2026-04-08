"""In-memory job / discrepancy store.

Mirrors the surface area of :mod:`app.core.demo_store` for documents,
queries, and insights, but keeps the structured job records the UI
needs for the History page and the "seen before" reasoning step on the
query engine. Separate from the demo store so we never accidentally
mix canned demo docs with real shop records.

This is deliberately tiny and thread-safe. Phase 5 swaps it for a
Postgres-backed repository with the same surface area.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from app.core.logging import get_logger

log = get_logger(__name__)


@dataclass
class JobStore:
    """Process-wide registry of discrepancy / job records."""

    _jobs: list[dict[str, Any]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    # ------------------------------------------------------------------
    def add(self, job: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            # Most-recent first.
            self._jobs.insert(0, job)
        log.info(
            "job_store: added job=%s aircraft=%s ata=%s doc=%s",
            job.get("id"),
            job.get("aircraft"),
            job.get("ata"),
            job.get("document_id"),
        )
        return job

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            for j in self._jobs:
                if j.get("id") == job_id:
                    return dict(j)
        return None

    def get_by_document(self, document_id: str) -> dict[str, Any] | None:
        with self._lock:
            for j in self._jobs:
                if j.get("document_id") == document_id:
                    return dict(j)
        return None

    def list(
        self,
        *,
        aircraft: str | None = None,
        tail_number: str | None = None,
        ata: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._jobs)
        if aircraft:
            items = [j for j in items if j.get("aircraft") == aircraft]
        if tail_number:
            items = [j for j in items if j.get("tail_number") == tail_number]
        if ata:
            items = [j for j in items if j.get("ata") == ata]
        if status:
            items = [j for j in items if j.get("status") == status]
        return items

    def reset(self) -> None:
        """Tests use this to start from an empty slate."""
        with self._lock:
            self._jobs.clear()

    def all(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._jobs)

    # ------------------------------------------------------------------
    def count(self) -> int:
        with self._lock:
            return len(self._jobs)


# ---------------------------------------------------------------------------
_store: JobStore | None = None
_store_lock = threading.Lock()


def get_job_store() -> JobStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = JobStore()
    return _store


def reset_job_store() -> None:
    """Test-only helper: swap in a fresh store."""
    global _store
    with _store_lock:
        _store = JobStore()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
