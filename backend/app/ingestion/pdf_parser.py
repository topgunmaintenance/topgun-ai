"""PDF parser stage.

Extracts per-page text from PDF uploads. The implementation:

- Lazy-imports PyMuPDF (``fitz``) so the MVP keeps working when the
  optional dependency isn't installed yet.
- Falls back to ``pdfplumber`` if PyMuPDF is missing but pdfplumber is
  available, so two backends share the same interface.
- For ``.txt`` / ``.md`` test fixtures it splits the file into pseudo
  pages so the rest of the pipeline can be exercised hermetically.
- Records per-page extraction metadata on the context so the OCR stage
  knows which pages need re-extraction and the chunker can flag the
  source quality on every chunk.

Real PDFs that the primary backend can't read are left empty *per page*
so the OCR stage can selectively rasterize only those pages.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from app.ingestion.pipeline import IngestionContext

log = get_logger(__name__)


@dataclass
class PageExtraction:
    """Per-page result from a parser backend."""

    page_number: int
    text: str
    source: str  # "pymupdf", "pdfplumber", "text", "empty"
    char_count: int

    @property
    def is_low_text(self) -> bool:
        return self.char_count < 40


class PdfParser:
    name = "pdf_parser"

    def run(self, ctx: "IngestionContext") -> None:
        path = ctx.source_path
        if not path.exists():
            from app.ingestion.pipeline import IngestionError

            raise IngestionError(self.name, f"source file missing: {path}")

        suffix = path.suffix.lower()

        if suffix in {".txt", ".md"}:
            text = path.read_text(errors="ignore")
            extractions = _from_plain_text(text)
        elif suffix == ".pdf":
            extractions = _extract_pdf(path)
        else:
            # Unknown binary: treat as a single empty page so OCR may try.
            extractions = [PageExtraction(1, "", "empty", 0)]

        ctx.pages = [e.text for e in extractions]
        ctx.page_extractions = [
            {
                "page_number": e.page_number,
                "source": e.source,
                "char_count": e.char_count,
                "needs_ocr": e.is_low_text,
            }
            for e in extractions
        ]
        ctx.extracted_fields["parser_backend"] = (
            extractions[0].source if extractions else "empty"
        )

        low_text = sum(1 for e in extractions if e.is_low_text)
        log.info(
            "pdf_parser: %s -> %d pages (%d low-text) via %s",
            path.name,
            len(extractions),
            low_text,
            ctx.extracted_fields["parser_backend"],
        )


# ---------------------------------------------------------------------------
# Backend dispatch
# ---------------------------------------------------------------------------
def _extract_pdf(path) -> list[PageExtraction]:  # noqa: ANN001
    backend = _pick_backend()
    if backend == "pymupdf":
        try:
            return _with_pymupdf(path)
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("pymupdf failed for %s: %s — trying pdfplumber", path.name, exc)
    if backend in {"pymupdf", "pdfplumber"}:
        try:
            return _with_pdfplumber(path)
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("pdfplumber failed for %s: %s", path.name, exc)
    # No backend available — record an empty page so OCR may attempt later.
    log.warning(
        "pdf_parser: no PDF backend installed (PyMuPDF / pdfplumber). "
        "OCR fallback will run on the document."
    )
    return [PageExtraction(1, "", "empty", 0)]


def _pick_backend() -> str:
    try:
        import fitz  # noqa: F401  # PyMuPDF

        return "pymupdf"
    except ImportError:
        pass
    try:
        import pdfplumber  # noqa: F401

        return "pdfplumber"
    except ImportError:
        return "none"


def _with_pymupdf(path) -> list[PageExtraction]:  # noqa: ANN001
    import fitz  # PyMuPDF

    out: list[PageExtraction] = []
    with fitz.open(str(path)) as doc:
        for index, page in enumerate(doc, start=1):
            text = page.get_text("text") or ""
            text = text.strip()
            out.append(
                PageExtraction(
                    page_number=index,
                    text=text,
                    source="pymupdf",
                    char_count=len(text),
                )
            )
    return out or [PageExtraction(1, "", "empty", 0)]


def _with_pdfplumber(path) -> list[PageExtraction]:  # noqa: ANN001
    import pdfplumber

    out: list[PageExtraction] = []
    with pdfplumber.open(str(path)) as pdf:
        for index, page in enumerate(pdf.pages, start=1):
            text = (page.extract_text() or "").strip()
            out.append(
                PageExtraction(
                    page_number=index,
                    text=text,
                    source="pdfplumber",
                    char_count=len(text),
                )
            )
    return out or [PageExtraction(1, "", "empty", 0)]


# ---------------------------------------------------------------------------
# Test fixture helper
# ---------------------------------------------------------------------------
def _from_plain_text(text: str, *, page_chars: int = 3000) -> list[PageExtraction]:
    if not text:
        return [PageExtraction(1, "", "text", 0)]
    pages: list[PageExtraction] = []
    for index, start in enumerate(range(0, len(text), page_chars), start=1):
        chunk = text[start : start + page_chars]
        pages.append(
            PageExtraction(
                page_number=index,
                text=chunk,
                source="text",
                char_count=len(chunk),
            )
        )
    return pages
