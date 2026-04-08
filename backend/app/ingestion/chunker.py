"""Chunker stage.

Splits page text into overlapping chunks that respect page boundaries
and carry **provenance**: page anchors, character offsets within the
page, content hash, approximate token count, and the parser backend
that produced the source text. The Source Drawer and citation builder
rely on these fields to render verifiable answers.

Default target: 800 "tokens" (approximated as 4 chars per token) with
120-token overlap. See ``docs/ingestion-pipeline.md`` for the rationale.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.core.logging import get_logger
from app.utils.text import normalize_whitespace

if TYPE_CHECKING:  # pragma: no cover
    from app.ingestion.pipeline import IngestionContext

log = get_logger(__name__)


@dataclass
class ChunkerConfig:
    target_tokens: int = 800
    overlap_tokens: int = 120
    chars_per_token: int = 4

    @property
    def target_chars(self) -> int:
        return self.target_tokens * self.chars_per_token

    @property
    def overlap_chars(self) -> int:
        return self.overlap_tokens * self.chars_per_token


class Chunker:
    name = "chunker"

    def __init__(self, config: ChunkerConfig | None = None) -> None:
        self.config = config or ChunkerConfig()

    def run(self, ctx: "IngestionContext") -> None:
        chunks: list[dict[str, Any]] = []
        for page_index, page_text in enumerate(ctx.pages, start=1):
            page_meta = _page_meta(ctx, page_index)
            for position, span in enumerate(self._split_page(page_text)):
                text = span["text"]
                normalized = normalize_whitespace(text)
                if not normalized:
                    continue
                chunk_id = f"{ctx.doc_id}_p{page_index}_c{position}"
                chunks.append(
                    {
                        "id": chunk_id,
                        "document_id": ctx.doc_id,
                        "page_start": page_index,
                        "page_end": page_index,
                        "position": position,
                        "char_start": span["start"],
                        "char_end": span["end"],
                        "char_count": len(text),
                        "token_estimate": max(1, len(text) // self.config.chars_per_token),
                        "content_hash": _hash(text),
                        "text": text,
                        "normalized_text": normalized,
                        "source": page_meta["source"],
                        "ocr": page_meta["source"] == "tesseract",
                    }
                )
        ctx.chunks = chunks
        log.info(
            "chunker: produced %d chunks from %d pages (ocr=%d)",
            len(chunks),
            len(ctx.pages),
            sum(1 for c in chunks if c["ocr"]),
        )

    # ------------------------------------------------------------------
    def _split_page(self, text: str) -> list[dict[str, Any]]:
        if not text:
            return []
        target = self.config.target_chars
        overlap = self.config.overlap_chars
        if len(text) <= target:
            return [{"text": text, "start": 0, "end": len(text)}]
        out: list[dict[str, Any]] = []
        start = 0
        while start < len(text):
            end = min(start + target, len(text))
            out.append({"text": text[start:end], "start": start, "end": end})
            if end == len(text):
                break
            start = end - overlap
        return out


# ---------------------------------------------------------------------------
def _hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def _page_meta(ctx: "IngestionContext", page_index: int) -> dict[str, Any]:
    extractions = ctx.page_extractions or []
    if 0 < page_index <= len(extractions):
        info = extractions[page_index - 1]
        return {
            "source": info.get("source", "unknown"),
            "char_count": info.get("char_count", 0),
        }
    return {"source": "unknown", "char_count": 0}
