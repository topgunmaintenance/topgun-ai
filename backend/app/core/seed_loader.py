"""Seed sample sources into the vector store at startup.

The repo ships a small fixture corpus under ``sample_data/sources/``
that demonstrates the multi-source federation flow end-to-end (the
Phenom 300 TOGA example). On startup we ingest those files through
the standard pipeline so the demo runs entirely on real retrieval —
no canned answers required.

The seed loader is idempotent and only runs when ``demo_mode`` is on.
Re-ingesting the same file is a no-op because the vector store keys
chunks by document id, and the document id is derived from the file
hash via the upload service.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import get_settings
from app.core.demo_store import DemoStore
from app.core.logging import get_logger
from app.core.source_family import family_for_doc_type
from app.ingestion.pipeline import IngestionPipeline
from app.retrieval.vector_store import get_vector_store

log = get_logger(__name__)


# Map a filename prefix to the declared document type used by the
# classifier. We hint here so the demo isn't dependent on whether the
# fixture text contains the magic keyword.
_TYPE_HINTS = {
    "_fim_": "FIM",
    "_amm_": "AMM",
    "_wdm_": "WDM",
    "_sb_": "SB",
    "_workorder_": "WORK_ORDER",
    "_logbook_": "LOGBOOK",
    "_ipc_": "IPC",
}


def _declared_type_for(name: str) -> str:
    lowered = name.lower()
    for needle, label in _TYPE_HINTS.items():
        if needle in lowered:
            return label
    return "UNKNOWN"


def seed_sources(store: DemoStore) -> int:
    """Ingest every fixture under ``sample_data/sources/``.

    Returns the number of documents indexed (skipped duplicates count
    as 1 because the upsert path keeps the doc record fresh).
    """
    settings = get_settings()
    sources_dir = settings.sample_data_dir / "sources"
    if not sources_dir.exists():
        log.info("seed_loader: no sample_data/sources directory; skipping")
        return 0

    pipeline = IngestionPipeline.default()
    indexed = 0
    for path in sorted(sources_dir.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".txt", ".md", ".pdf"}:
            continue
        declared_type = _declared_type_for(path.name)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        doc_id = f"seed_{digest}"

        result = pipeline.run(
            doc_id=doc_id,
            source_path=path,
            title=_pretty_title(path.name),
            doc_type=declared_type,
            source="sample_data/sources",
        )

        fields = result.extracted_fields
        family = fields.get("source_family") or family_for_doc_type(
            result.classified_type
        )
        doc = {
            "id": doc_id,
            "title": _pretty_title(path.name),
            "type": result.classified_type,
            "source_family": family,
            "aircraft": fields.get("aircraft_model"),
            "aircraft_model": fields.get("aircraft_model"),
            "source": "sample_data/sources",
            "url": None,
            "vendor": None,
            "document_code": fields.get("document_code"),
            "revision": fields.get("revision"),
            "ata": list(fields.get("ata_chapters") or []),
            "components": list(fields.get("components") or []),
            "captured_at": None,
            "status": "indexed" if result.indexed else "failed",
            "pages": result.page_count,
            "size_mb": round(path.stat().st_size / (1024 * 1024), 3),
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "uploaded_by": "demo_seed",
            "tags": ["demo", family.lower(), "phenom-300"]
            if fields.get("aircraft_model") == "Phenom 300"
            else ["demo", family.lower()],
            "summary": result.summary,
            "ingestion": {
                "parser_backend": result.parser_backend,
                "page_count": result.page_count,
                "chunk_count": result.chunk_count,
                "indexed": result.indexed,
                "ocr_applied": result.ocr_applied,
                "ocr_pages": list(result.ocr_pages),
                "extracted_fields": dict(fields),
                "error": result.error,
            },
        }
        store.upsert_document(doc)
        if result.indexed:
            indexed += 1

    log.info("seed_loader: indexed %d demo source documents", indexed)
    # And surface the number of unique families now available.
    families = {
        m.get("source_family")
        for m in get_vector_store().all_metadata()
        if m.get("source_family")
    }
    log.info("seed_loader: indexed source families = %s", sorted(families))
    return indexed


def _pretty_title(filename: str) -> str:
    stem = Path(filename).stem.replace("_", " ").title()
    return stem
