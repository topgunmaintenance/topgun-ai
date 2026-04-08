"""Answer formatter.

Turns merged chunks + a question into a structured answer shape. The
formatter is **strict**:

- If there are no retrieved chunks, it refuses to invent anything and
  returns an ``insufficient`` confidence response.
- If the strongest chunk is below a configurable score floor, it
  downgrades the confidence label and explains why in the reason text.
- Snippets are normalized and truncated so the UI never receives a
  multi-page paragraph.
- Source-quality flags (OCR, parser backend) are surfaced so the UI
  can call out citations that came from low-confidence text.

Phase 2 will call the configured AI provider with a tightly-bounded
prompt that lists only the retrieved chunks and enforces JSON output.
For now the implementation is deterministic so the UI always gets a
shape-correct response and tests stay hermetic.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.utils.text import normalize_whitespace, truncate

# Cosine score below which we treat a hit as weak signal. Hits below
# this still appear in the citations list (so the user can verify) but
# the confidence label drops to ``low`` and the answer says so.
WEAK_SCORE_FLOOR = 0.18

# Below this even the strongest hit isn't enough to claim an answer.
INSUFFICIENT_SCORE_FLOOR = 0.05

SNIPPET_CHARS = 280


@dataclass
class FormatterConfig:
    weak_score_floor: float = WEAK_SCORE_FLOOR
    insufficient_score_floor: float = INSUFFICIENT_SCORE_FLOOR
    snippet_chars: int = SNIPPET_CHARS


class AnswerFormatter:
    def __init__(self, config: FormatterConfig | None = None) -> None:
        self.config = config or FormatterConfig()

    # ------------------------------------------------------------------
    def format(
        self, *, question: str, chunks: list[dict[str, Any]]
    ) -> dict[str, Any]:
        if not chunks:
            return self._insufficient(reason="No chunks retrieved.")

        top_score = max((float(c.get("score", 0.0)) for c in chunks), default=0.0)

        if top_score < self.config.insufficient_score_floor:
            return self._insufficient(
                reason=(
                    f"Best match scored {top_score:.2f}, below the floor of "
                    f"{self.config.insufficient_score_floor:.2f}. Refusing to answer."
                )
            )

        weak = top_score < self.config.weak_score_floor
        snippets = [
            truncate(normalize_whitespace(c.get("snippet", "")), self.config.snippet_chars)
            for c in chunks[:3]
        ]
        snippets = [s for s in snippets if s]

        score, label, reason = self._confidence(chunks, weak=weak, top_score=top_score)
        return {
            "answer": self._answer_text(snippets=snippets, weak=weak),
            "sections": [
                {
                    "heading": "Retrieved evidence",
                    "bullets": snippets,
                },
                {
                    "heading": "Source quality",
                    "bullets": _quality_bullets(chunks),
                },
            ],
            "related_documents": _related(chunks),
            "entities": [],
            "confidence": {"score": score, "label": label, "reason": reason},
            "followups": [
                f"Show the full passage from {chunks[0].get('document_title', 'this source')}.",
                "List related maintenance write-ups.",
            ],
        }

    # ------------------------------------------------------------------
    def _insufficient(self, *, reason: str) -> dict[str, Any]:
        return {
            "answer": (
                "I could not find evidence for this question in the indexed "
                "sources. Upload the relevant manual or maintenance record and "
                "ask again."
            ),
            "sections": [
                {
                    "heading": "What Topgun AI did",
                    "bullets": [
                        "Searched the manual, history, parts, and pattern lanes.",
                        "Did not find any chunks above the evidence floor.",
                        "Refused to answer from model priors — source-first policy.",
                    ],
                }
            ],
            "related_documents": [],
            "entities": [],
            "confidence": {
                "score": 0.0,
                "label": "insufficient",
                "reason": reason,
            },
            "followups": [
                "Upload the relevant manual chapter and retry.",
                "Narrow the question to a specific aircraft or ATA chapter.",
            ],
        }

    @staticmethod
    def _answer_text(*, snippets: list[str], weak: bool) -> str:
        if not snippets:
            return (
                "Topgun AI found candidate chunks but none contained usable text. "
                "Re-upload the source or try a more specific question."
            )
        prefix = (
            "Evidence is weak — verify these passages against the source before acting."
            if weak
            else "Based on the retrieved sources, the most relevant evidence is:"
        )
        return prefix + "\n\n- " + "\n- ".join(snippets)

    def _confidence(
        self,
        chunks: list[dict[str, Any]],
        *,
        weak: bool,
        top_score: float,
    ) -> tuple[float, str, str]:
        # Combine evidence breadth (chunk count) with strength (top score).
        breadth = min(1.0, len(chunks) / 6.0)
        score = round(min(1.0, 0.5 * top_score * 5 + 0.5 * breadth), 4)
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
        reason = (
            f"Fused {len(chunks)} chunks across lanes; top score {top_score:.2f}."
        )
        return score, label, reason


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
        if len(out) >= 4:
            break
    return out


def _quality_bullets(chunks: list[dict[str, Any]]) -> list[str]:
    backends: dict[str, int] = {}
    ocr_count = 0
    for c in chunks[:6]:
        backend = c.get("source") or "unknown"
        backends[backend] = backends.get(backend, 0) + 1
        if c.get("ocr"):
            ocr_count += 1
    bullets: list[str] = []
    for backend, count in sorted(backends.items(), key=lambda kv: -kv[1]):
        bullets.append(f"{count} chunks via {backend}")
    if ocr_count:
        bullets.append(
            f"{ocr_count} chunks came from OCR — verify spelling-sensitive details"
        )
    return bullets or ["No source-quality metadata available."]
