"""Source coverage detector.

Given a ``QueryIntent`` and the metadata for everything currently
indexed in the vector store + connectors, this module decides which
source families are *likely needed* to answer the question and which
of those are *missing* from the operator's connected sources.

The output is a list of ``CoverageGap`` objects that the answer
formatter renders as a "Missing likely sources" section.

The detector never invents what a missing manual would say. It only
explains what kind of manual is likely needed and why.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.core.source_family import (
    SourceFamily,
    family_for_doc_type,
    label_for,
)
from app.query.intent_classifier import QueryIntent


# How many of the top-priority families to consider "likely needed".
DEFAULT_LIKELY_TOP_N = 4

# Vendor hints we surface in the missing-sources message when a system
# is mentioned but no matching vendor manual is connected. Kept small
# and conservative — we never *recommend* a brand we don't know about.
_VENDOR_HINTS_BY_SYSTEM: dict[str, list[str]] = {
    "autoflight": ["Garmin", "Honeywell Primus", "Collins Pro Line"],
    "avionics": ["Garmin", "Honeywell", "Collins"],
    "electrical": [],
    "hydraulics": [],
    "powerplant": ["Pratt & Whitney", "Honeywell"],
}


@dataclass
class CoverageGap:
    family: SourceFamily
    label: str
    reason: str
    vendor_hint: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "family": self.family,
            "label": self.label,
            "reason": self.reason,
            "vendor_hint": self.vendor_hint,
        }


@dataclass
class CoverageReport:
    likely_families: list[SourceFamily]
    available_families: list[SourceFamily]
    missing_families: list[SourceFamily]
    gaps: list[CoverageGap]

    def to_dict(self) -> dict[str, object]:
        return {
            "likely_families": list(self.likely_families),
            "available_families": list(self.available_families),
            "missing_families": list(self.missing_families),
            "gaps": [g.to_dict() for g in self.gaps],
        }


# ---------------------------------------------------------------------------
# Reasons — kept here so they're consistent and tested.
# ---------------------------------------------------------------------------
_REASON_BY_FAMILY: dict[SourceFamily, str] = {
    "FIM": (
        "A Fault Isolation Manual usually carries the step-by-step "
        "troubleshooting flow for this symptom; without it, only "
        "general AMM procedures are searchable."
    ),
    "WDM": (
        "A Wiring Diagram Manual is needed to trace circuits, "
        "connectors, and pinouts for an electrical or autoflight fault."
    ),
    "AMM": (
        "The Aircraft Maintenance Manual provides the formal removal, "
        "installation, and adjustment procedures for any corrective "
        "action this answer would suggest."
    ),
    "IPC": (
        "The Illustrated Parts Catalog is needed to confirm the part "
        "number, applicability, and effectivity before ordering or "
        "swapping a component."
    ),
    "SB": (
        "Service Bulletins disclose fleet-wide notices, mandatory mods, "
        "and superseded procedures that may already address this fault."
    ),
    "HISTORY": (
        "Internal maintenance history (work orders, logbook entries) "
        "is needed to see if this aircraft has shown the same symptom "
        "before."
    ),
    "BROWSER": (
        "No browser-derived manual content has been pushed in for this "
        "aircraft / system. Connect your authenticated manual portal "
        "and push the relevant page."
    ),
    "EXTERNAL": (
        "No authorized external connector is configured for this "
        "vendor's portal."
    ),
    "OTHER": "Additional reference material may be needed.",
}


# ---------------------------------------------------------------------------
class CoverageDetector:
    """Decide which families are likely needed and which are missing."""

    def __init__(self, likely_top_n: int = DEFAULT_LIKELY_TOP_N) -> None:
        self.likely_top_n = likely_top_n

    def detect(
        self,
        *,
        intent: QueryIntent,
        available_families: Iterable[str],
    ) -> CoverageReport:
        available = sorted(
            {fam for fam in available_families if fam}
        )
        likely = self._likely_families(intent)
        missing = [fam for fam in likely if fam not in available]

        gaps: list[CoverageGap] = []
        for family in missing:
            reason = _REASON_BY_FAMILY.get(family, _REASON_BY_FAMILY["OTHER"])
            vendor_hint = self._vendor_hint(family, intent)
            gaps.append(
                CoverageGap(
                    family=family,
                    label=label_for(family),
                    reason=reason,
                    vendor_hint=vendor_hint,
                )
            )
        return CoverageReport(
            likely_families=likely,
            available_families=list(available),
            missing_families=missing,
            gaps=gaps,
        )

    # ------------------------------------------------------------------
    def _likely_families(self, intent: QueryIntent) -> list[SourceFamily]:
        """The intent classifier already orders families by weight."""
        priority = list(intent.family_priority)
        # Always exclude the catch-all OTHER bucket from "likely needed".
        priority = [f for f in priority if f != "OTHER"]
        return priority[: self.likely_top_n]

    @staticmethod
    def _vendor_hint(family: SourceFamily, intent: QueryIntent) -> str | None:
        """Suggest a vendor manual when the symptom strongly implies one."""
        if family not in {"BROWSER", "EXTERNAL", "FIM", "WDM"}:
            return None
        for system in intent.system_hints:
            hints = _VENDOR_HINTS_BY_SYSTEM.get(system, [])
            if hints:
                # Return the first hint plus the system context — never
                # invent a part number or torque value, just the manual
                # type.
                return f"{hints[0]} {system} manual or portal"
        return None


# ---------------------------------------------------------------------------
def families_from_metadata(
    metadata_records: Iterable[dict],
) -> list[SourceFamily]:
    """Helper: derive the available family set from a list of metadata dicts."""
    out: set[SourceFamily] = set()
    for meta in metadata_records:
        family = meta.get("source_family")
        if family:
            out.add(family)  # type: ignore[arg-type]
        else:
            # Fall back to mapping the document type if family wasn't set.
            out.add(family_for_doc_type(meta.get("type")))
    return sorted(out)
