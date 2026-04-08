"""OCR fallback stage.

Re-runs text extraction on any pages the primary parser flagged as
``low_text``. The implementation:

- Lazy-imports ``pytesseract`` and ``PIL`` so the MVP keeps working when
  the optional dependencies aren't installed yet.
- Rasterizes individual pages with PyMuPDF (already a dependency of the
  primary parser when installed) so we don't shell out to ``pdftoppm``.
- Touches only the pages flagged by ``pdf_parser`` — never re-OCRs pages
  that already have good text. This keeps cost bounded and provenance
  honest.
- Stamps each rebuilt page with ``source="tesseract"`` so the chunker
  can carry an ``ocr=True`` flag forward to citations.

When dependencies are missing, the stage records that OCR was skipped
rather than silently producing empty content.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from app.ingestion.pipeline import IngestionContext

log = get_logger(__name__)


class OcrProcessor:
    name = "ocr_processor"

    def run(self, ctx: "IngestionContext") -> None:
        targets = [
            (i, info)
            for i, info in enumerate(ctx.page_extractions)
            if info.get("needs_ocr")
        ]
        if not targets:
            ctx.extracted_fields.setdefault("ocr_applied", False)
            log.info("ocr_processor: nothing to OCR")
            return

        path = ctx.source_path
        if path.suffix.lower() != ".pdf":
            # The fixture path: we can't rasterize a .txt file. Mark the
            # pages as ocr-skipped and move on.
            ctx.extracted_fields["ocr_applied"] = False
            ctx.extracted_fields["ocr_skipped_reason"] = (
                f"non-PDF source ({path.suffix})"
            )
            log.info("ocr_processor: skipped non-PDF source %s", path.name)
            return

        backend = _pick_backend()
        if backend != "ready":
            ctx.extracted_fields["ocr_applied"] = False
            ctx.extracted_fields["ocr_skipped_reason"] = backend
            log.warning(
                "ocr_processor: dependency missing (%s); leaving %d low-text pages empty",
                backend,
                len(targets),
            )
            return

        try:
            updated, total_chars = _ocr_pages(path, [i for i, _ in targets])
        except Exception as exc:  # pragma: no cover - defensive
            ctx.extracted_fields["ocr_applied"] = False
            ctx.extracted_fields["ocr_skipped_reason"] = f"ocr_error: {exc}"
            log.error("ocr_processor: OCR failed: %s", exc)
            return

        for (index, info), text in zip(targets, updated):
            ctx.pages[index] = text
            info["source"] = "tesseract"
            info["char_count"] = len(text)
            info["needs_ocr"] = len(text) < 40

        ctx.extracted_fields["ocr_applied"] = True
        ctx.extracted_fields["ocr_pages"] = [i + 1 for i, _ in targets]
        ctx.extracted_fields["ocr_chars"] = total_chars
        log.info(
            "ocr_processor: OCRed %d pages (%d chars total)",
            len(targets),
            total_chars,
        )


# ---------------------------------------------------------------------------
def _pick_backend() -> str:
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return "missing pytesseract"
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        return "missing Pillow"
    try:
        import fitz  # noqa: F401
    except ImportError:
        return "missing PyMuPDF (needed to rasterize pages)"
    return "ready"


def _ocr_pages(path, page_indices: list[int]) -> tuple[list[str], int]:  # noqa: ANN001
    """Rasterize the requested pages and run tesseract on each.

    ``page_indices`` are 0-based indices into the document.
    """
    import io

    import fitz  # PyMuPDF
    import pytesseract
    from PIL import Image

    targets = set(page_indices)
    out_by_index: dict[int, str] = {}

    with fitz.open(str(path)) as doc:
        for i, page in enumerate(doc):
            if i not in targets:
                continue
            # 200 DPI gives a reasonable trade-off for typical aviation scans.
            pix = page.get_pixmap(dpi=200)
            image = Image.open(io.BytesIO(pix.tobytes("png")))
            text = pytesseract.image_to_string(image) or ""
            out_by_index[i] = text.strip()

    ordered = [out_by_index.get(i, "") for i in page_indices]
    return ordered, sum(len(t) for t in ordered)
