"""Google Drive connector — search files and export readable text."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from opencrab.integrations.base import SourceDocument, SourceFetchError

_DRIVE_API = "https://www.googleapis.com/drive/v3"

_EXPORT_MIME = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}

_TEXT_MIME_PREFIXES = ("text/",)
_TEXT_MIME_EXACT = {
    "application/json",
    "application/xml",
    "application/javascript",
    "application/x-markdown",
    "application/md",
}


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "User-Agent": "OpenCrab-Integrations",
    }


def _get(client: httpx.Client, url: str, **kwargs: Any) -> httpx.Response:
    response = client.get(url, **kwargs)
    if response.status_code >= 400:
        raise SourceFetchError(
            f"Google Drive API error {response.status_code}: {response.text[:300]}",
            status_code=response.status_code,
        )
    return response


def _is_text_file(mime: str) -> bool:
    if mime in _TEXT_MIME_EXACT:
        return True
    return any(mime.startswith(prefix) for prefix in _TEXT_MIME_PREFIXES)


def _read_file_text(client: httpx.Client, file_id: str, mime: str) -> str:
    if mime in _EXPORT_MIME:
        export_mime = _EXPORT_MIME[mime]
        response = _get(
            client,
            f"{_DRIVE_API}/files/{quote(file_id)}/export",
            params={"mimeType": export_mime},
        )
        return response.text

    if _is_text_file(mime):
        response = _get(
            client,
            f"{_DRIVE_API}/files/{quote(file_id)}",
            params={"alt": "media"},
        )
        return response.text

    return ""


def fetch_gdrive_documents(
    *,
    access_token: str,
    query: str | None = None,
    source_url: str | None = None,
    max_items: int = 25,
    client: httpx.Client | None = None,
) -> list[SourceDocument]:
    """
    List/search Drive files and ingest exported text content.

    `source_url` may be a Drive file id or a standard drive.google.com link.
    """
    owns_client = client is None
    client = client or httpx.Client(timeout=30.0, headers=_headers(access_token))
    docs: list[SourceDocument] = []

    try:
        file_ids: list[str] = []

        if source_url:
            file_id = _extract_file_id(source_url)
            if file_id:
                file_ids.append(file_id)

        if not file_ids:
            q_parts = ["trashed = false"]
            if query:
                safe = query.replace("\\", "\\\\").replace("'", "\\'")
                q_parts.append(f"fullText contains '{safe}'")
            params = {
                "pageSize": min(max_items, 25),
                "fields": "files(id,name,mimeType,webViewLink)",
                "q": " and ".join(q_parts),
            }
            payload = _get(client, f"{_DRIVE_API}/files", params=params).json()
            for item in payload.get("files") or []:
                file_ids.append(item["id"])

        seen: set[str] = set()
        for file_id in file_ids:
            if file_id in seen or len(docs) >= max_items:
                continue
            seen.add(file_id)
            meta = _get(
                client,
                f"{_DRIVE_API}/files/{quote(file_id)}",
                params={"fields": "id,name,mimeType,webViewLink"},
            ).json()
            mime = meta.get("mimeType") or ""
            text = _read_file_text(client, file_id, mime).strip()
            if not text:
                continue
            title = meta.get("name") or file_id
            docs.append(
                SourceDocument(
                    external_id=f"gdrive:{file_id}",
                    title=title,
                    text=f"# {title}\n\n{text}",
                    url=meta.get("webViewLink"),
                    metadata={"source": "gdrive", "file_id": file_id, "mime_type": mime},
                )
            )
    finally:
        if owns_client:
            client.close()

    return docs


def _extract_file_id(value: str) -> str | None:
    value = value.strip()
    if "/" not in value and " " not in value and len(value) >= 10:
        return value
    markers = ["/d/", "id="]
    for marker in markers:
        if marker in value:
            chunk = value.split(marker, 1)[1]
            return chunk.split("/")[0].split("?")[0].split("&")[0]
    return None
