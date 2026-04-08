"""Rank-fusion utilities.

Merges the results of multiple retrieval lanes using reciprocal rank
fusion with per-lane weights, then returns a single ordered list.

Two scores travel with each merged hit:

- ``retrieval_score`` — the strongest *raw* similarity score the chunk
  achieved in any contributing lane. This is the number the answer
  formatter should use to decide whether evidence is strong, weak, or
  insufficient, because RRF scores are tiny by design and not
  comparable across query shapes.
- ``score`` — the fused RRF score, used only for ordering.
"""
from __future__ import annotations

from typing import Any

LaneHits = dict[str, list[dict[str, Any]]]


def reciprocal_rank_fusion(
    lanes: LaneHits,
    *,
    k: int = 60,
    weights: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Return chunks merged across lanes, ordered by fused score."""
    weights = weights or {}
    buckets: dict[str, dict[str, Any]] = {}

    for lane, hits in lanes.items():
        weight = weights.get(lane, 1.0)
        for rank, hit in enumerate(hits, start=1):
            key = _key(hit)
            raw_score = float(hit.get("score", 0.0))
            bucket = buckets.get(key)
            if bucket is None:
                bucket = {
                    **hit,
                    "lanes": set(),
                    "score": 0.0,
                    "retrieval_score": raw_score,
                }
                buckets[key] = bucket
            else:
                if raw_score > bucket.get("retrieval_score", 0.0):
                    bucket["retrieval_score"] = raw_score
            bucket["lanes"].add(lane)
            bucket["score"] += weight / (k + rank)

    merged = list(buckets.values())
    merged.sort(key=lambda h: h["score"], reverse=True)
    for m in merged:
        m["lanes"] = sorted(m["lanes"])
    return merged


def _key(hit: dict[str, Any]) -> str:
    return hit.get("id") or f'{hit.get("document_id")}:{hit.get("page")}'
