"""Notion connector — search pages and extract plain text."""

from __future__ import annotations

from typing import Any

import httpx

from opencrab.integrations.base import SourceDocument, SourceFetchError

_NOTION_API = "https://api.notion.com/v1"
_NOTION_VERSION = "2022-06-28"


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": _NOTION_VERSION,
        "Content-Type": "application/json",
        "User-Agent": "OpenCrab-Integrations",
    }


def _rich_text(parts: list[dict[str, Any]] | None) -> str:
    if not parts:
        return ""
    return "".join(part.get("plain_text", "") for part in parts)


def _block_to_text(block: dict[str, Any]) -> str:
    block_type = block.get("type")
    if not block_type:
        return ""
    data = block.get(block_type) or {}
    if block_type in {
        "paragraph",
        "heading_1",
        "heading_2",
        "heading_3",
        "bulleted_list_item",
        "numbered_list_item",
        "quote",
        "callout",
        "toggle",
        "to_do",
    }:
        return _rich_text(data.get("rich_text"))
    if block_type == "code":
        return _rich_text(data.get("rich_text"))
    if block_type == "child_page":
        return data.get("title") or ""
    return ""


def _page_title(page: dict[str, Any]) -> str:
    props = page.get("properties") or {}
    for value in props.values():
        if value.get("type") == "title":
            title = _rich_text(value.get("title"))
            if title:
                return title
    return page.get("id", "Untitled")


def _get_json(client: httpx.Client, method: str, url: str, **kwargs: Any) -> Any:
    response = client.request(method, url, **kwargs)
    if response.status_code >= 400:
        raise SourceFetchError(
            f"Notion API error {response.status_code}: {response.text[:300]}",
            status_code=response.status_code,
        )
    return response.json()


def _fetch_page_text(client: httpx.Client, page_id: str, *, max_blocks: int = 100) -> str:
    lines: list[str] = []
    cursor: str | None = None
    fetched = 0
    while fetched < max_blocks:
        params: dict[str, Any] = {"page_size": min(50, max_blocks - fetched)}
        if cursor:
            params["start_cursor"] = cursor
        payload = _get_json(client, "GET", f"{_NOTION_API}/blocks/{page_id}/children", params=params)
        for block in payload.get("results") or []:
            text = _block_to_text(block).strip()
            if text:
                lines.append(text)
            fetched += 1
            if fetched >= max_blocks:
                break
        if not payload.get("has_more"):
            break
        cursor = payload.get("next_cursor")
        if not cursor:
            break
    return "\n".join(lines)


def fetch_notion_documents(
    *,
    access_token: str,
    query: str | None = None,
    source_url: str | None = None,
    max_items: int = 25,
    client: httpx.Client | None = None,
) -> list[SourceDocument]:
    """Search Notion pages (and optionally resolve a page URL/id) then ingest text."""
    owns_client = client is None
    client = client or httpx.Client(timeout=30.0, headers=_headers(access_token))
    docs: list[SourceDocument] = []

    try:
        page_ids: list[tuple[str, dict[str, Any]]] = []

        if source_url and "notion.so" in source_url:
            # Notion page URLs end with a 32-char hex id (often with hyphens).
            compact = "".join(ch for ch in source_url.split("?")[0].split("-")[-1] if ch.isalnum())
            if len(compact) >= 32:
                page_id = compact[-32:]
                page_id = f"{page_id[:8]}-{page_id[8:12]}-{page_id[12:16]}-{page_id[16:20]}-{page_id[20:]}"
                page = _get_json(client, "GET", f"{_NOTION_API}/pages/{page_id}")
                page_ids.append((page_id, page))

        if not page_ids:
            body: dict[str, Any] = {
                "page_size": min(max_items, 25),
                "filter": {"value": "page", "property": "object"},
            }
            if query:
                body["query"] = query
            payload = _get_json(client, "POST", f"{_NOTION_API}/search", json=body)
            for page in payload.get("results") or []:
                if page.get("object") != "page":
                    continue
                page_ids.append((page["id"], page))
                if len(page_ids) >= max_items:
                    break

        for page_id, page in page_ids[:max_items]:
            title = _page_title(page)
            text = _fetch_page_text(client, page_id).strip()
            if not text:
                text = title
            docs.append(
                SourceDocument(
                    external_id=f"notion:{page_id}",
                    title=title,
                    text=f"# {title}\n\n{text}",
                    url=page.get("url"),
                    metadata={"source": "notion", "page_id": page_id},
                )
            )
    finally:
        if owns_client:
            client.close()

    return docs
