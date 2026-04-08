"""Field extractor stage.

Extracts structured fields (tail number, ATA chapter, part numbers,
dates, aircraft model, components, document code, revision) from the
parsed text. The implementation is regex-driven, deterministic, and
small enough to test exhaustively. A Phase-4 upgrade can replace it
with an Anthropic structured-extraction call without changing the
interface.
"""
from __future__ import annotations

import re

from app.core.logging import get_logger
from app.core.source_family import family_for_doc_type

log = get_logger(__name__)

_TAIL_RE = re.compile(r"\bN[0-9]{1,5}[A-Z]{0,2}\b")
_ATA_RE = re.compile(r"\bATA\s?(\d{2})\b", re.IGNORECASE)
_PN_RE = re.compile(r"\b[0-9]{3,}-[0-9A-Z]{2,}(?:-[0-9A-Z]+)?\b")
_DATE_RE = re.compile(r"\b(20\d{2})-(0[1-9]|1[0-2])-([0-2]\d|3[01])\b")
_REVISION_RE = re.compile(r"\b(?:rev(?:ision)?\.?)\s*([0-9]{1,4}[A-Z]?)\b", re.IGNORECASE)
_DOCCODE_RE = re.compile(
    r"\b([A-Z]{2,4}-?\d{2,4}(?:-\d{2,4})*)\b"
)  # e.g. AMM-29-11-05, FIM 22-10-00, SB-29-04
_SB_RE = re.compile(r"\b(SB[- ]?\d{2,4}[- ]?\d{0,4}[A-Z]?)\b", re.IGNORECASE)


# Aircraft model patterns. Kept in sync with the intent classifier table
# but exposed here so it works on document text rather than questions.
_AIRCRAFT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Phenom 300", re.compile(r"\bphenom\s*300\b", re.IGNORECASE)),
    ("Phenom 100", re.compile(r"\bphenom\s*100\b", re.IGNORECASE)),
    ("Citation XLS", re.compile(r"\bcitation\s*xls\b", re.IGNORECASE)),
    ("Citation CJ3", re.compile(r"\b(citation\s*cj3|cj3)\b", re.IGNORECASE)),
    ("King Air 350", re.compile(r"\bking\s*air\s*350\b", re.IGNORECASE)),
    ("King Air 200", re.compile(r"\bking\s*air\s*200\b", re.IGNORECASE)),
    ("Pilatus PC-12", re.compile(r"\bpc[- ]?12\b", re.IGNORECASE)),
    ("Gulfstream G450", re.compile(r"\bg\s*450\b", re.IGNORECASE)),
    ("Gulfstream G550", re.compile(r"\bg\s*550\b", re.IGNORECASE)),
]


# Component / system table. Used to tag chunks so retrieval can do an
# additional component-based filter on top of similarity.
_COMPONENT_PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    ("TOGA switch", "autoflight", re.compile(r"\btoga\b", re.IGNORECASE)),
    ("Autopilot", "autoflight", re.compile(r"\bautopilot|autoflight\b", re.IGNORECASE)),
    ("Hydraulic system", "hydraulics", re.compile(r"\bhydraulic|reservoir\b", re.IGNORECASE)),
    ("Landing gear", "landing gear", re.compile(r"\blanding\s*gear|mlg|nlg\b", re.IGNORECASE)),
    ("Electrical wiring", "electrical", re.compile(r"\bharness|connector|pinout|wir(e|ing)\b", re.IGNORECASE)),
    ("Engine", "powerplant", re.compile(r"\bengine|n1|n2|itt\b", re.IGNORECASE)),
    ("Fuel system", "fuel", re.compile(r"\bfuel\b", re.IGNORECASE)),
    ("Avionics", "avionics", re.compile(r"\bavionics|fmc|fms\b", re.IGNORECASE)),
]


class FieldExtractor:
    name = "field_extractor"

    def run(self, ctx) -> None:  # noqa: ANN001
        text = "\n".join(ctx.pages)
        tail_numbers = sorted(set(_TAIL_RE.findall(text)))
        ata_chapters = sorted({m.group(1) for m in _ATA_RE.finditer(text)})
        part_numbers = sorted(set(_PN_RE.findall(text)))
        dates = sorted({"-".join(m.groups()) for m in _DATE_RE.finditer(text)})
        revision = self._first(_REVISION_RE, text)
        sb_codes = sorted({m.group(1) for m in _SB_RE.finditer(text)})
        document_code = self._first(_DOCCODE_RE, text)
        aircraft_model = self._aircraft_model(text)
        components, systems = self._components(text)

        # Source family follows the (already-set) classified type.
        source_family = family_for_doc_type(ctx.classified_type)

        ctx.extracted_fields.update(
            {
                "tail_numbers": tail_numbers,
                "ata_chapters": ata_chapters,
                "part_numbers": part_numbers[:50],
                "dates": dates,
                "aircraft_model": aircraft_model,
                "components": components,
                "systems": systems,
                "document_code": document_code,
                "revision": revision,
                "service_bulletins": sb_codes,
                "source_family": source_family,
            }
        )
        log.info(
            "field_extractor: tails=%d ata=%d parts=%d dates=%d aircraft=%s family=%s",
            len(tail_numbers),
            len(ata_chapters),
            len(part_numbers),
            len(dates),
            aircraft_model,
            source_family,
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _first(pattern: re.Pattern[str], text: str) -> str | None:
        m = pattern.search(text)
        if not m:
            return None
        return m.group(1) if m.groups() else m.group(0)

    @staticmethod
    def _aircraft_model(text: str) -> str | None:
        for label, pattern in _AIRCRAFT_PATTERNS:
            if pattern.search(text):
                return label
        return None

    @staticmethod
    def _components(text: str) -> tuple[list[str], list[str]]:
        components: list[str] = []
        systems: list[str] = []
        for component, system, pattern in _COMPONENT_PATTERNS:
            if pattern.search(text):
                if component not in components:
                    components.append(component)
                if system not in systems:
                    systems.append(system)
        return components, systems
