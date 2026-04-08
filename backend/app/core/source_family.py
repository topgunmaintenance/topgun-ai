"""Source family taxonomy.

Topgun AI ingests many *kinds* of maintenance content. The pipeline
classifies each document into a ``DocumentType`` (AMM / IPC / SB / ...),
but retrieval, ranking, and the UI all need to reason about a coarser
*source family* — the kind of intelligence the document represents.

A source family answers a different operator question:

- ``FIM`` — "what's the troubleshooting flow for this symptom?"
- ``WDM`` — "where's the wire / connector / pin?"
- ``AMM`` — "what's the maintenance procedure?"
- ``IPC`` — "what part do I order?"
- ``SB``  — "is there a fleet-wide notice on this?"
- ``HISTORY`` — "have we seen this on this aircraft before?"
- ``EXTERNAL`` — "is there an authorized OEM portal entry?"

The source family is what the query engine uses to federate retrieval
across lanes and what the answer formatter uses to produce grouped
evidence sections in the UI.
"""
from __future__ import annotations

from typing import Final, Iterable, Literal

SourceFamily = Literal[
    "FIM",
    "WDM",
    "AMM",
    "IPC",
    "SB",
    "HISTORY",
    "BROWSER",
    "EXTERNAL",
    "OTHER",
]

ALL_SOURCE_FAMILIES: Final[tuple[SourceFamily, ...]] = (
    "FIM",
    "WDM",
    "AMM",
    "IPC",
    "SB",
    "HISTORY",
    "BROWSER",
    "EXTERNAL",
    "OTHER",
)


# DocumentType -> SourceFamily
_TYPE_TO_FAMILY: Final[dict[str, SourceFamily]] = {
    "FIM": "FIM",
    "TROUBLESHOOTING": "FIM",
    "WDM": "WDM",
    "WM": "WDM",
    "WIRING_DIAGRAM": "WDM",
    "AMM": "AMM",
    "INSPECTION_PROGRAM": "AMM",
    "IPC": "IPC",
    "PARTS_CATALOG": "IPC",
    "SB": "SB",
    "ALERT_BULLETIN": "SB",
    "WORK_ORDER": "HISTORY",
    "LOGBOOK": "HISTORY",
    "DISCREPANCY": "HISTORY",
    "BROWSER": "BROWSER",
    "BROWSER_CAPTURE": "BROWSER",
    "BROWSER_PAGE": "BROWSER",
    "EXTERNAL": "EXTERNAL",
    "UNKNOWN": "OTHER",
}


# Default per-family priority weights when no intent override applies.
# These get scaled by the intent classifier so that, e.g., a
# troubleshooting question lifts FIM/WDM and demotes IPC.
DEFAULT_FAMILY_WEIGHTS: Final[dict[SourceFamily, float]] = {
    "FIM": 1.30,
    "WDM": 1.10,
    "AMM": 1.05,
    "IPC": 0.85,
    "SB": 0.90,
    "HISTORY": 0.80,
    "BROWSER": 0.95,
    "EXTERNAL": 0.70,
    "OTHER": 0.50,
}


# Human-readable labels used by the UI / answer formatter section
# headings. Kept here so the labels stay in sync with the taxonomy.
FAMILY_LABELS: Final[dict[SourceFamily, str]] = {
    "FIM": "Troubleshooting",
    "WDM": "Wiring / Electrical",
    "AMM": "Maintenance Procedure",
    "IPC": "Parts / Components",
    "SB": "Service Bulletins",
    "HISTORY": "Internal History",
    "BROWSER": "Browser-derived results",
    "EXTERNAL": "External / OEM Portal",
    "OTHER": "Other",
}


def family_for_doc_type(doc_type: str | None) -> SourceFamily:
    """Map a ``DocumentType`` to its canonical ``SourceFamily``.

    Unknown / missing types fall through to ``OTHER`` so the rest of
    the pipeline never crashes on a new label.
    """
    if not doc_type:
        return "OTHER"
    return _TYPE_TO_FAMILY.get(doc_type.upper(), "OTHER")


def families_in_priority_order(
    weights: dict[SourceFamily, float] | None = None,
) -> list[SourceFamily]:
    """Return families ordered by descending priority weight."""
    table = weights or DEFAULT_FAMILY_WEIGHTS
    return sorted(table, key=lambda f: -table[f])


def known_doc_types_for(family: SourceFamily) -> list[str]:
    """Return the document type labels that map to a given family."""
    return sorted(t for t, f in _TYPE_TO_FAMILY.items() if f == family)


def label_for(family: SourceFamily) -> str:
    return FAMILY_LABELS.get(family, family)


def normalize(families: Iterable[str]) -> list[SourceFamily]:
    """Defensive normalizer: keep only families in the canonical set."""
    out: list[SourceFamily] = []
    valid = set(ALL_SOURCE_FAMILIES)
    for f in families:
        upper = (f or "").upper()
        if upper in valid:
            out.append(upper)  # type: ignore[arg-type]
    return out
