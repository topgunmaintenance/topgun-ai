"""Answer formatter.

Turns merged chunks + a question into a structured answer shape.
Phase 3 makes the formatter family-aware:

- Evidence is grouped by source family (Troubleshooting, Wiring,
  Maintenance Procedure, Parts, Bulletins, Browser-derived, History).
- A short "likely troubleshooting path" is composed from the
  highest-priority family that returned hits.
- A "Missing likely sources" section is appended whenever the coverage
  detector flagged at least one missing family. The text never invents
  what the missing manual would say — it explains why it would help.

The formatter is **strict**:

- If there are no retrieved chunks, it refuses to invent anything and
  returns an ``insufficient`` confidence response (still with the
  missing-sources section so the user knows what to connect).
- If the strongest chunk is below the score floor, the confidence
  label drops to ``low`` with an explicit reason.
- Snippets are normalized and truncated.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from app.core.source_family import (
    ALL_SOURCE_FAMILIES,
    SourceFamily,
    label_for,
)
from app.query.coverage import CoverageGap, CoverageReport
from app.query.intent_classifier import QueryIntent
from app.utils.text import normalize_whitespace, truncate

WEAK_SCORE_FLOOR = 0.18
INSUFFICIENT_SCORE_FLOOR = 0.05
SNIPPET_CHARS = 280


@dataclass
class FormatterConfig:
    weak_score_floor: float = WEAK_SCORE_FLOOR
    insufficient_score_floor: float = INSUFFICIENT_SCORE_FLOOR
    snippet_chars: int = SNIPPET_CHARS


# Display order for grouped sections in the UI.
_FAMILY_DISPLAY_ORDER: tuple[SourceFamily, ...] = (
    "FIM",
    "WDM",
    "AMM",
    "IPC",
    "SB",
    "BROWSER",
    "HISTORY",
    "EXTERNAL",
    "OTHER",
)


class AnswerFormatter:
    def __init__(self, config: FormatterConfig | None = None) -> None:
        self.config = config or FormatterConfig()

    # ------------------------------------------------------------------
    def format(
        self,
        *,
        question: str,
        chunks: list[dict[str, Any]],
        intent: QueryIntent | None = None,
        coverage: CoverageReport | None = None,
    ) -> dict[str, Any]:
        if not chunks:
            return self._insufficient(
                reason="No chunks retrieved.",
                intent=intent,
                coverage=coverage,
            )

        top_score = max(
            (
                float(c.get("retrieval_score", c.get("score", 0.0)))
                for c in chunks
            ),
            default=0.0,
        )
        if top_score < self.config.insufficient_score_floor:
            return self._insufficient(
                reason=(
                    f"Best match scored {top_score:.2f}, below the floor of "
                    f"{self.config.insufficient_score_floor:.2f}. Refusing to answer."
                ),
                intent=intent,
                coverage=coverage,
            )

        weak = top_score < self.config.weak_score_floor
        grouped = self._group_by_family(chunks)
        sections = self._sections(grouped, weak=weak, top_score=top_score)
        if coverage and coverage.gaps:
            sections.append(self._missing_section(coverage.gaps))

        score, label, reason = self._confidence(
            chunks, weak=weak, top_score=top_score, coverage=coverage
        )

        return {
            "answer": self._answer_text(
                grouped=grouped,
                weak=weak,
                intent=intent,
                coverage=coverage,
            ),
            "troubleshooting_path": self._troubleshooting_path(grouped, intent),
            "sections": sections,
            "related_documents": _related(chunks),
            "entities": _entities(chunks, intent),
            "confidence": {"score": score, "label": label, "reason": reason},
            "followups": self._followups(chunks, coverage),
        }

    # ------------------------------------------------------------------
    # Insufficient path
    # ------------------------------------------------------------------
    def _insufficient(
        self,
        *,
        reason: str,
        intent: QueryIntent | None,
        coverage: CoverageReport | None,
    ) -> dict[str, Any]:
        sections: list[dict[str, Any]] = [
            {
                "heading": "What Topgun AI did",
                "family": None,
                "bullets": [
                    "Classified the question and predicted the likely source families.",
                    "Searched every connected source family and external connector.",
                    "Found no chunks above the evidence floor.",
                    "Refused to answer from model priors — source-first policy.",
                ],
            }
        ]
        if coverage and coverage.gaps:
            sections.append(self._missing_section(coverage.gaps))
        return {
            "answer": (
                "I could not find evidence for this question in the connected "
                "sources. Connect the missing manuals listed below or upload the "
                "relevant PDF / push the relevant browser page, then ask again."
            ),
            "troubleshooting_path": [],
            "sections": sections,
            "related_documents": [],
            "entities": _entities([], intent),
            "confidence": {
                "score": 0.0,
                "label": "insufficient",
                "reason": reason,
            },
            "followups": [
                "Upload the relevant manual chapter and retry.",
                "Push the relevant browser-portal page from the extension.",
                "Narrow the question to a specific aircraft or ATA chapter.",
            ],
        }

    # ------------------------------------------------------------------
    # Section building
    # ------------------------------------------------------------------
    @staticmethod
    def _group_by_family(
        chunks: Iterable[dict[str, Any]],
    ) -> dict[SourceFamily, list[dict[str, Any]]]:
        grouped: dict[SourceFamily, list[dict[str, Any]]] = {}
        for c in chunks:
            family: SourceFamily = c.get("source_family") or "OTHER"  # type: ignore[assignment]
            if family not in ALL_SOURCE_FAMILIES:
                family = "OTHER"
            grouped.setdefault(family, []).append(c)
        return grouped

    def _sections(
        self,
        grouped: dict[SourceFamily, list[dict[str, Any]]],
        *,
        weak: bool,
        top_score: float,
    ) -> list[dict[str, Any]]:
        sections: list[dict[str, Any]] = []
        for family in _FAMILY_DISPLAY_ORDER:
            family_chunks = grouped.get(family) or []
            if not family_chunks:
                continue
            bullets = [
                self._snippet_for(c) for c in family_chunks[:3]
            ]
            bullets = [b for b in bullets if b]
            sections.append(
                {
                    "heading": label_for(family),
                    "family": family,
                    "bullets": bullets,
                }
            )
        if weak:
            sections.append(
                {
                    "heading": "Evidence quality",
                    "family": None,
                    "bullets": [
                        f"Top retrieval score is {top_score:.2f} — treat as weak.",
                        "Verify each citation against the source before acting.",
                    ],
                }
            )
        return sections

    def _snippet_for(self, chunk: dict[str, Any]) -> str:
        snippet = truncate(
            normalize_whitespace(chunk.get("snippet", "")),
            self.config.snippet_chars,
        )
        if not snippet:
            return ""
        title = chunk.get("document_title") or chunk.get("document_id", "source")
        page = chunk.get("page")
        marker = f"[{title}"
        if page:
            marker += f" p.{page}"
        marker += "]"
        return f"{snippet}  {marker}"

    @staticmethod
    def _missing_section(gaps: list[CoverageGap]) -> dict[str, Any]:
        bullets = []
        for gap in gaps:
            line = f"{gap.label}: {gap.reason}"
            if gap.vendor_hint:
                line += f" (suggested: {gap.vendor_hint})"
            bullets.append(line)
        return {
            "heading": "Missing likely sources",
            "family": None,
            "bullets": bullets,
        }

    # ------------------------------------------------------------------
    # Answer text + troubleshooting path
    # ------------------------------------------------------------------
    @staticmethod
    def _troubleshooting_path(
        grouped: dict[SourceFamily, list[dict[str, Any]]],
        intent: QueryIntent | None,
    ) -> list[str]:
        # The path comes from the highest-priority family that returned
        # hits, in the order the chunks were ranked. Limit to 4 steps.
        family_order = (
            (intent.family_priority if intent else None)
            or list(_FAMILY_DISPLAY_ORDER)
        )
        for family in family_order:
            chunks = grouped.get(family) or []
            if not chunks:
                continue
            steps: list[str] = []
            for c in chunks[:4]:
                snippet = normalize_whitespace(c.get("snippet", ""))
                if not snippet:
                    continue
                steps.append(truncate(snippet, 200))
            if steps:
                return steps
        return []

    def _answer_text(
        self,
        *,
        grouped: dict[SourceFamily, list[dict[str, Any]]],
        weak: bool,
        intent: QueryIntent | None,
        coverage: CoverageReport | None,
    ) -> str:
        path = self._troubleshooting_path(grouped, intent)
        prefix = (
            "Evidence is weak — verify these passages against the source before acting."
            if weak
            else "Based on the connected sources, the most relevant evidence is:"
        )
        body = prefix
        if path:
            body += "\n\nLikely troubleshooting path:\n- " + "\n- ".join(path)
        if coverage and coverage.gaps:
            missing = ", ".join(g.label for g in coverage.gaps)
            body += (
                f"\n\nNote: this answer is incomplete because the following "
                f"likely sources are not connected: {missing}."
            )
        return body

    # ------------------------------------------------------------------
    def _confidence(
        self,
        chunks: list[dict[str, Any]],
        *,
        weak: bool,
        top_score: float,
        coverage: CoverageReport | None,
    ) -> tuple[float, str, str]:
        breadth = min(1.0, len(chunks) / 6.0)
        score = round(min(1.0, 0.5 * top_score * 5 + 0.5 * breadth), 4)

        # Penalize when likely sources are missing — even if retrieval
        # was strong, we shouldn't claim "high" confidence on a partial
        # picture.
        if coverage and coverage.gaps:
            penalty = min(0.25, 0.05 * len(coverage.gaps))
            score = round(max(0.0, score - penalty), 4)

        if weak:
            label = "low"
            reason = (
                f"Top match scored {top_score:.2f} (weak). Treat as a starting "
                f"point only and verify against the source."
            )
            return min(score, 0.45), label, reason
        if score >= 0.7:
            label = "high"
        elif score >= 0.5:
            label = "medium"
        else:
            label = "low"
        reason_parts = [
            f"Fused {len(chunks)} chunks across families; top score {top_score:.2f}."
        ]
        if coverage and coverage.gaps:
            reason_parts.append(
                f"Confidence reduced because {len(coverage.gaps)} likely "
                f"source(s) are not connected."
            )
        return score, label, " ".join(reason_parts)

    # ------------------------------------------------------------------
    @staticmethod
    def _followups(
        chunks: list[dict[str, Any]],
        coverage: CoverageReport | None,
    ) -> list[str]:
        out: list[str] = []
        if chunks:
            top = chunks[0]
            out.append(
                f"Show the full passage from {top.get('document_title', 'this source')}."
            )
        if coverage and coverage.gaps:
            for gap in coverage.gaps[:2]:
                out.append(f"Connect a {gap.label} source to improve this answer.")
        out.append("List related maintenance write-ups.")
        return out


# ---------------------------------------------------------------------------
def _related(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for c in chunks:
        doc_id = c.get("document_id")
        if not doc_id or doc_id in seen:
            continue
        seen.add(doc_id)
        out.append(
            {
                "id": doc_id,
                "title": c.get("document_title", doc_id),
                "type": c.get("document_type", "UNKNOWN"),
            }
        )
        if len(out) >= 5:
            break
    return out


def _entities(
    chunks: list[dict[str, Any]], intent: QueryIntent | None
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if intent:
        if intent.aircraft:
            out.append({"kind": "aircraft", "value": intent.aircraft})
        for ata in intent.ata_hints[:4]:
            out.append({"kind": "ata", "value": ata})
    for c in chunks[:6]:
        for ata in (c.get("ata") or [])[:2]:
            entry = {"kind": "ata", "value": ata}
            if entry not in out:
                out.append(entry)
        title = c.get("document_title")
        if title and not any(o.get("value") == title for o in out):
            # We deliberately do not invent extracted_entities here.
            pass
    return out
