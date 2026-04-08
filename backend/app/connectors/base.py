"""Connector framework — interface, registry, and a default stub."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol

from app.core.logging import get_logger

log = get_logger(__name__)


@dataclass
class ConnectorHit:
    """A single result returned by an external connector.

    The shape mirrors a fused ``chunk`` so the query engine can drop
    these directly into the rank-fusion stage without special-casing.
    """

    id: str
    document_id: str
    document_title: str
    document_type: str  # e.g. "EXTERNAL"
    snippet: str
    score: float
    page: int = 1
    char_start: int = 0
    char_end: int = 0
    source_family: str = "EXTERNAL"
    url: str | None = None
    vendor: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_chunk(self) -> dict[str, Any]:
        """Return the dict shape that the rank fusion stage expects."""
        return {
            "id": self.id,
            "document_id": self.document_id,
            "document_title": self.document_title,
            "document_type": self.document_type,
            "page": self.page,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "snippet": self.snippet,
            "score": float(self.score),
            "lane": "external",
            "source": "external",
            "ocr": False,
            "source_family": self.source_family,
            "vendor": self.vendor,
            "url": self.url,
            **self.metadata,
        }


class Connector(Protocol):
    """Authorized external source adapter.

    Implementations must be cheap to instantiate and *must not* perform
    network calls in ``__init__``. They are expected to honor the
    operator's allow-list and to return at most ``top_k`` results.
    """

    name: str
    enabled: bool

    def search(
        self,
        *,
        question: str,
        intent: Any,  # QueryIntent — typed Any to avoid an import cycle
        top_k: int = 5,
    ) -> list[ConnectorHit]:
        ...


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
class ConnectorRegistry:
    """Process-wide registry of authorized external connectors.

    Empty by default. Operators wire connectors in by either:

    - Calling ``register()`` from application start-up code, or
    - Calling :func:`set_registry` with a fully constructed registry.

    Tests can swap the registry with :func:`set_registry` to inject
    fakes without monkey-patching.
    """

    def __init__(self, connectors: Iterable[Connector] | None = None) -> None:
        self._connectors: list[Connector] = list(connectors or [])

    def register(self, connector: Connector) -> None:
        # Replace by name if it already exists.
        self._connectors = [c for c in self._connectors if c.name != connector.name]
        self._connectors.append(connector)
        log.info("connector registered: %s (enabled=%s)", connector.name, connector.enabled)

    def all(self) -> list[Connector]:
        return list(self._connectors)

    def enabled(self) -> list[Connector]:
        return [c for c in self._connectors if getattr(c, "enabled", False)]

    def search(
        self,
        *,
        question: str,
        intent: Any,
        top_k: int = 5,
    ) -> list[ConnectorHit]:
        """Fan out across all enabled connectors and merge their hits."""
        hits: list[ConnectorHit] = []
        for connector in self.enabled():
            try:
                hits.extend(connector.search(question=question, intent=intent, top_k=top_k))
            except Exception as exc:  # pragma: no cover - defensive
                log.warning("connector %s raised: %s", connector.name, exc)
        return hits


# ---------------------------------------------------------------------------
# Stub connector — kept here so the federation path is always exercised
# ---------------------------------------------------------------------------
class StubExternalConnector:
    """A no-op connector used in tests and for the empty default state.

    Returns no hits unless ``hits`` is provided at construction time,
    in which case those hits are returned verbatim. The point is to
    prove the wiring works without making network calls.
    """

    def __init__(
        self,
        *,
        name: str = "stub_external",
        enabled: bool = False,
        hits: list[ConnectorHit] | None = None,
    ) -> None:
        self.name = name
        self.enabled = enabled
        self._hits = list(hits or [])

    def search(
        self,
        *,
        question: str,
        intent: Any,
        top_k: int = 5,
    ) -> list[ConnectorHit]:
        return list(self._hits)[:top_k]


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_registry: ConnectorRegistry | None = None


def get_registry() -> ConnectorRegistry:
    global _registry
    if _registry is None:
        _registry = ConnectorRegistry()
    return _registry


def set_registry(registry: ConnectorRegistry | None) -> None:
    """Replace the process-wide registry. Pass ``None`` to reset."""
    global _registry
    _registry = registry
