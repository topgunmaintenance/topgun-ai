"""Keyword-based document classifier.

The stub uses simple keyword heuristics over filename and first-page
text. Phase 1 replaces this with a small classifier (LLM or fine-tuned
model) while keeping the same interface.
"""
from __future__ import annotations

from app.core.logging import get_logger

log = get_logger(__name__)


_KEYWORDS: dict[str, tuple[str, ...]] = {
    "FIM": (
        "fault isolation",
        "fim",
        "troubleshoot",
        "isolation manual",
        "maintenance message",
    ),
    "WDM": (
        "wiring diagram",
        "wdm",
        "wiring manual",
        "schematic",
        "connector view",
        "pinout",
    ),
    "AMM": ("maintenance manual", "amm", "aircraft maintenance"),
    "IPC": ("illustrated parts", "ipc", "parts catalog"),
    "SB": ("service bulletin", "sb-", "alert bulletin"),
    "WORK_ORDER": ("work order", "wo-", "discrepancy", "corrective action"),
    "LOGBOOK": ("logbook", "log book", "aircraft log"),
    "PARTS_CATALOG": ("parts list",),
    "INSPECTION_PROGRAM": ("inspection program", "phase inspection", "task card"),
    "BROWSER_CAPTURE": ("browser capture", "captured from browser"),
}


class DocumentClassifier:
    name = "document_classifier"

    def run(self, ctx) -> None:  # noqa: ANN001
        if ctx.declared_type and ctx.declared_type != "UNKNOWN":
            ctx.classified_type = ctx.declared_type
            log.info(
                "document_classifier: using declared type %s", ctx.declared_type
            )
            return

        sample = " ".join(ctx.pages[:2] + [ctx.source_path.name]).lower()
        for label, keywords in _KEYWORDS.items():
            if any(kw in sample for kw in keywords):
                ctx.classified_type = label
                log.info("document_classifier: classified as %s", label)
                return

        ctx.classified_type = "UNKNOWN"
        log.info("document_classifier: no heuristic match — UNKNOWN")
