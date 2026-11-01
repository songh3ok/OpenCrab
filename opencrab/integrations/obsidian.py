"""Obsidian connector — Local REST API plugin and public markdown vault URLs."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote, urljoin

import httpx

from opencrab.integrations.base import SourceDocument, SourceFetchError

_DEFAULT_LOCAL_API = "http://127.0.0.1:27123"


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "User-Agent": "OpenCrab-Integrations",
    }


def _request(client: httpx.Client, method: str, url: str, **kwargs: Any) -> httpx.Response:
    response = client.request(method, url, **kwargs)
    if response.status_code >= 400:
        raise SourceFetchError(
            f"Obsidian API error {response.status_code}: {response.text[:300]}",
            status_code=response.status_code,
        )
    return response


def fetch_obsidian_documents(
    *,
    access_token: str,
    query: str | None = None,
    source_url: str | None = None,
    max_items: int = 25,
    client: httpx.Client | None = None,
) -> list[SourceDocument]:
    """
    Fetch notes from an Obsidian vault via the Local REST API plugin.

    - `access_token`: API key configured in the Obsidian Local REST API plugin
    - `source_url`: optional base URL (defaults to http://127.0.0.1:27123)
    - `query`: optional search string; without it, vault file listing is used
    """
    base = (source_url or _DEFAULT_LOCAL_API).rstrip("/") + "/"
    owns_client = client is None
    client = client or httpx.Client(timeout=30.0, headers=_headers(access_token))
    docs: list[SourceDocument] = []

    try:
        paths: list[str] = []

        if query:
            # Local REST API search endpoint
            response = _request(
                client,
                "POST",
                urljoin(base, "search/simple/"),
                json={"query": query},
            )
            payload = response.json()
            if isinstance(payload, list):
                for hit in payload:
                    filename = hit.get("filename") if isinstance(hit, dict) else None
                    if filename:
                        paths.append(filename)
            elif isinstance(payload, dict):
                for hit in payload.get("results") or payload.get("files") or []:
                    if isinstance(hit, str):
                        paths.append(hit)
                    elif isinstance(hit, dict) and hit.get("filename"):
                        paths.append(hit["filename"])
        else:
            response = _request(client, "GET", urljoin(base, "vault/"))
            listing = response.json()
            files = listing.get("files") if isinstance(listing, dict) else listing
            for entry in files or []:
                name = entry if isinstance(entry, str) else entry.get("path") or entry.get("name")
                if not name:
                    continue
                if name.lower().endswith((".md", ".txt", ".markdown")):
                    paths.append(name)

        seen: set[str] = set()
        for path in paths:
            normalized = path.lstrip("/")
            if normalized in seen or len(docs) >= max_items:
                continue
            if not normalized.lower().endswith((".md", ".txt", ".markdown")):
                continue
            seen.add(normalized)
            response = _request(client, "GET", urljoin(base, f"vault/{quote(normalized)}"))
            # Prefer plain text; fall back to JSON body fields if present.
            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type:
                payload = response.json()
                text = (
                    payload.get("content")
                    or payload.get("text")
                    or payload.get("data")
                    or ""
                )
                if isinstance(text, dict):
                    text = text.get("content") or ""
                text = str(text)
            else:
                text = response.text
            text = text.strip()
            if not text:
                continue
            title = normalized.rsplit("/", 1)[-1]
            docs.append(
                SourceDocument(
                    external_id=f"obsidian:{normalized}",
                    title=title,
                    text=text,
                    url=urljoin(base, f"vault/{quote(normalized)}"),
                    metadata={"source": "obsidian", "path": normalized},
                )
            )
    finally:
        if owns_client:
            client.close()

    return docs
