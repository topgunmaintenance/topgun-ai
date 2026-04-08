"""Citation builder.

Transforms fused chunk hits into the ``Citation`` shape the query
response uses. Carries enough provenance for the Source Drawer to
deep-link straight to the relevant part of the source:

- ``page``                — anchor for "open page N"
- ``char_start`` / ``char_end`` — range inside the page text
- ``source``              — which parser produced the text (pymupdf, ocr, …)
- ``ocr``                 — true when the chunk came from OCR; the UI uses
                            this to show a "verify against source" warning
- ``score``               — fused retrieval score, clamped to [0, 1]
- ``weak``                — whether the score is below the evidence floor
"""
from __future__ import annotations

from typing import Any

from app.utils.text import normalize_whitespace, truncate

WEAK_SCORE_FLOOR = 0.18
SNIPPET_CHARS = 280


def build_citations(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    for chunk in chunks:
        # Prefer the raw retrieval similarity over the RRF fused score so
        # the UI shows a number that's actually comparable across queries.
        score = float(chunk.get("retrieval_score", chunk.get("score", 0.0)))
        score = max(0.0, min(1.0, score))
        snippet = truncate(
            normalize_whitespace(chunk.get("snippet", "")), SNIPPET_CHARS
        )
        components = chunk.get("components") or []
        component = components[0] if components else None
        citations.append(
            {
                "document_id": chunk["document_id"],
                "document_title": chunk.get("document_title", chunk["document_id"]),
                "document_type": chunk.get("document_type", "UNKNOWN"),
                "source_family": chunk.get("source_family"),
                "page": int(chunk.get("page", 1)),
                "char_start": int(chunk.get("char_start", 0)),
                "char_end": int(chunk.get("char_end", 0)),
                "snippet": snippet,
                "score": score,
                "lane": _primary_lane(chunk),
                "source": chunk.get("source", "unknown"),
                "aircraft_model": chunk.get("aircraft_model"),
                "ata": list(chunk.get("ata") or []),
                "component": component,
                "document_code": chunk.get("document_code"),
                "url": chunk.get("url"),
                "vendor": chunk.get("vendor"),
                "ocr": bool(chunk.get("ocr", False)),
                "weak": score < WEAK_SCORE_FLOOR,
            }
        )
    return citations


def _primary_lane(chunk: dict[str, Any]) -> str:
    lanes = chunk.get("lanes")
    if lanes:
        return lanes[0]
    return chunk.get("lane", "manual")
