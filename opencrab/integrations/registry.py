"""Dispatch table for external source connectors."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from opencrab.integrations.base import SourceDocument, SourceFetchError
from opencrab.integrations.gdrive import fetch_gdrive_documents
from opencrab.integrations.github import fetch_github_documents
from opencrab.integrations.notion import fetch_notion_documents
from opencrab.integrations.obsidian import fetch_obsidian_documents

SOURCE_TYPES = ("obsidian", "notion", "gdrive", "github")

Fetcher = Callable[..., list[SourceDocument]]

_FETCHERS: dict[str, Fetcher] = {
    "obsidian": fetch_obsidian_documents,
    "notion": fetch_notion_documents,
    "gdrive": fetch_gdrive_documents,
    "github": fetch_github_documents,
}


def fetch_source_documents(
    source_type: str,
    *,
    access_token: str,
    query: str | None = None,
    source_url: str | None = None,
    max_items: int = 25,
    client: httpx.Client | None = None,
) -> list[SourceDocument]:
    """Fetch documents for a supported source type."""
    key = source_type.strip().lower()
    fetcher = _FETCHERS.get(key)
    if fetcher is None:
        raise SourceFetchError(
            f"Unsupported source_type '{source_type}'. Expected one of: {', '.join(SOURCE_TYPES)}",
            status_code=400,
        )
    if not access_token or not access_token.strip():
        raise SourceFetchError("access_token is required for source ingest.", status_code=400)

    capped = max(1, min(int(max_items or 25), 50))
    return fetcher(
        access_token=access_token.strip(),
        query=query,
        source_url=source_url,
        max_items=capped,
        client=client,
    )
