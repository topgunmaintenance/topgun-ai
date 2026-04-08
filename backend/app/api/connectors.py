"""Connector endpoints.

Currently exposes the browser push transport. The browser extension /
local helper / Playwright driver all POST to ``/api/connectors/browser/push``
with the same shape — see :class:`BrowserPushRequest` below.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.connectors.browser import BrowserPushIngestor, BrowserPushPayload
from app.core.config import get_settings
from app.ingestion.pipeline import IngestionPipeline
from app.retrieval.vector_store import get_vector_store

router = APIRouter(prefix="/connectors", tags=["connectors"])


class BrowserPushRequest(BaseModel):
    """Push payload from a browser extension or local helper."""

    title: str = Field(min_length=2, max_length=512)
    text: str = Field(min_length=10)
    url: str | None = None
    aircraft: str | None = None
    document_code: str | None = None
    revision: str | None = None
    vendor: str | None = None
    declared_type: str = "BROWSER_CAPTURE"
    captured_at: datetime | None = None
    notes: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


def get_browser_push_ingestor() -> BrowserPushIngestor:
    settings = get_settings()
    return BrowserPushIngestor(
        pipeline=IngestionPipeline.default(),
        upload_dir=settings.upload_dir / "browser",
        vector_store=get_vector_store(),
    )


@router.post("/browser/push")
def push_browser_page(
    request: BrowserPushRequest,
    ingestor: BrowserPushIngestor = Depends(get_browser_push_ingestor),
) -> dict[str, Any]:
    """Ingest text + metadata pushed from an authenticated browser tab."""
    try:
        result = ingestor.ingest(
            BrowserPushPayload(
                title=request.title,
                text=request.text,
                url=request.url,
                aircraft=request.aircraft,
                document_code=request.document_code,
                revision=request.revision,
                vendor=request.vendor,
                declared_type=request.declared_type or "BROWSER_CAPTURE",
                captured_at=request.captured_at,
                notes=request.notes,
                extra=request.extra,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "indexed", **result}
