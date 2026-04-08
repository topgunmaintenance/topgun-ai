"""Content-overlap gate for retrieval hits.

The stub embedder used in demo mode hashes tokens into buckets, so two
completely unrelated strings can still score a small non-zero cosine
similarity through hash collisions. That's good enough for demos where
the question and the manual share real content tokens — but it means
totally off-topic questions can return top-K results that *look*
confident to the answer formatter.

This module applies a cheap keyword-overlap gate as a floor: if the
question and a retrieved chunk do not share at least one content token
(>=3 chars, not a stopword), the chunk is dropped. This gives the
formatter a clean "no evidence" signal on nonsense questions, which in
turn lets the confidence layer downgrade honestly.

The gate is deliberately *additive*: it never promotes a hit, it only
suppresses hits that clearly don't belong.
"""
from __future__ import annotations

from typing import Any, Iterable

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by",
    "can", "do", "does", "for", "from", "have", "has", "how",
    "in", "into", "is", "it", "its", "of", "on", "onto", "or",
    "our", "out", "so", "than", "that", "the", "their", "then",
    "there", "these", "they", "this", "those", "to", "too",
    "under", "up", "was", "were", "what", "when", "where",
    "which", "who", "why", "will", "with", "without", "you",
    "your", "yours", "me", "my", "mine", "not", "no", "yes",
    "show", "find", "related", "across", "fleet", "please",
}


def content_tokens(text: str) -> set[str]:
    """Return lowercase content tokens (non-stopword, len>=3)."""
    cleaned = "".join(c if c.isalnum() else " " for c in text.lower())
    return {
        tok
        for tok in cleaned.split()
        if len(tok) >= 3 and tok not in _STOPWORDS
    }


def has_overlap(question_tokens: set[str], chunk: dict[str, Any]) -> bool:
    """True if the chunk shares at least one content token with the question.

    We check the snippet, document title, document code, ATA hints, and
    component list so a question like "ATA 22 troubleshooting" still
    matches a chunk whose snippet happens to not include the literal
    numbers.
    """
    haystack: list[str] = []
    snippet = chunk.get("snippet") or ""
    haystack.append(str(snippet))
    haystack.append(str(chunk.get("document_title") or ""))
    haystack.append(str(chunk.get("document_code") or ""))
    haystack.append(str(chunk.get("aircraft_model") or ""))
    haystack.append(str(chunk.get("vendor") or ""))
    for ata in chunk.get("ata") or []:
        haystack.append(str(ata))
    for comp in chunk.get("components") or []:
        haystack.append(str(comp))
    chunk_tokens = content_tokens(" ".join(haystack))
    return bool(question_tokens & chunk_tokens)


def apply_overlap_gate(
    question: str, hits: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Drop hits that share zero content tokens with the question."""
    q_tokens = content_tokens(question)
    if not q_tokens:
        # If the question has no content tokens at all (pure stopwords or
        # punctuation) we can't reason about overlap — let the formatter
        # floor handle it.
        return list(hits)
    return [h for h in hits if has_overlap(q_tokens, h)]
