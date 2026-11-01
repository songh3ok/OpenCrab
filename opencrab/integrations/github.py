"""GitHub connector — search repositories / code and ingest readable text."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from opencrab.integrations.base import SourceDocument, SourceFetchError

_REPO_RE = re.compile(r"^[\w.-]+/[\w.-]+$")
_GITHUB_API = "https://api.github.com"


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "OpenCrab-Integrations",
    }


def _parse_repo(source_url: str | None, query: str | None) -> str | None:
    if source_url:
        parsed = urlparse(source_url)
        parts = [p for p in parsed.path.strip("/").split("/") if p]
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1]}"
    if query and _REPO_RE.match(query.strip()):
        return query.strip()
    return None


def _decode_content(payload: dict[str, Any]) -> str:
    import base64

    encoding = payload.get("encoding")
    content = payload.get("content") or ""
    if encoding == "base64":
        return base64.b64decode(content).decode("utf-8", errors="replace")
    return str(content)


def _get_json(client: httpx.Client, url: str, *, params: dict[str, Any] | None = None) -> Any:
    response = client.get(url, params=params)
    if response.status_code >= 400:
        detail = response.text[:300]
        raise SourceFetchError(
            f"GitHub API error {response.status_code}: {detail}",
            status_code=response.status_code,
        )
    return response.json()


def fetch_github_documents(
    *,
    access_token: str,
    query: str | None = None,
    source_url: str | None = None,
    max_items: int = 25,
    client: httpx.Client | None = None,
) -> list[SourceDocument]:
    """
    Fetch documents from GitHub.

    Modes:
    - `owner/repo` via query or source_url → README + matching markdown/text files
    - free-text query → GitHub code search hits (decoded when available)
    """
    owns_client = client is None
    client = client or httpx.Client(timeout=30.0, headers=_headers(access_token))
    docs: list[SourceDocument] = []

    try:
        repo = _parse_repo(source_url, query)
        if repo:
            docs.extend(_fetch_repo_documents(client, repo, query=query, max_items=max_items))
        elif query:
            docs.extend(_fetch_code_search(client, query, max_items=max_items))
        else:
            raise SourceFetchError(
                "GitHub ingest requires query (search term or owner/repo) or source_url.",
                status_code=400,
            )
    finally:
        if owns_client:
            client.close()

    return docs[:max_items]


def _fetch_repo_documents(
    client: httpx.Client,
    repo: str,
    *,
    query: str | None,
    max_items: int,
) -> list[SourceDocument]:
    docs: list[SourceDocument] = []

    try:
        readme = _get_json(client, f"{_GITHUB_API}/repos/{repo}/readme")
        text = _decode_content(readme).strip()
        if text:
            docs.append(
                SourceDocument(
                    external_id=f"github:{repo}:readme",
                    title=f"{repo} README",
                    text=text,
                    url=readme.get("html_url"),
                    metadata={"source": "github", "repo": repo, "path": readme.get("path", "README")},
                )
            )
    except SourceFetchError as exc:
        if exc.status_code not in {404}:
            raise

    tree = _get_json(
        client,
        f"{_GITHUB_API}/repos/{repo}/git/trees/HEAD",
        params={"recursive": "1"},
    )
    entries = tree.get("tree") or []
    candidates = [
        entry
        for entry in entries
        if entry.get("type") == "blob"
        and isinstance(entry.get("path"), str)
        and entry["path"].lower().endswith((".md", ".txt", ".rst", ".markdown"))
    ]

    needle = None
    if query and not _REPO_RE.match(query.strip()):
        needle = query.strip().lower()

    if needle:
        candidates = [c for c in candidates if needle in c["path"].lower()]

    for entry in candidates:
        if len(docs) >= max_items:
            break
        path = entry["path"]
        file_payload = _get_json(
            client,
            f"{_GITHUB_API}/repos/{repo}/contents/{quote(path, safe='/')}",
        )
        if isinstance(file_payload, list):
            continue
        text = _decode_content(file_payload).strip()
        if not text:
            continue
        docs.append(
            SourceDocument(
                external_id=f"github:{repo}:{path}",
                title=path,
                text=text,
                url=file_payload.get("html_url"),
                metadata={"source": "github", "repo": repo, "path": path},
            )
        )

    return docs


def _fetch_code_search(client: httpx.Client, query: str, *, max_items: int) -> list[SourceDocument]:
    payload = _get_json(
        client,
        f"{_GITHUB_API}/search/code",
        params={"q": query, "per_page": min(max_items, 30)},
    )
    docs: list[SourceDocument] = []
    for item in payload.get("items") or []:
        if len(docs) >= max_items:
            break
        html_url = item.get("html_url")
        path = item.get("path") or "file"
        repo_full = (item.get("repository") or {}).get("full_name") or "unknown"
        text_parts = [f"# {repo_full}/{path}"]
        if html_url:
            text_parts.append(html_url)
        # Code search does not return file bodies without an extra contents call.
        api_url = item.get("url")
        if api_url:
            try:
                file_payload = _get_json(client, api_url)
                body = _decode_content(file_payload).strip()
                if body:
                    text_parts.append(body[:8000])
            except SourceFetchError:
                text_parts.append(item.get("name") or path)
        docs.append(
            SourceDocument(
                external_id=f"github-search:{repo_full}:{path}",
                title=f"{repo_full}/{path}",
                text="\n\n".join(text_parts),
                url=html_url,
                metadata={"source": "github", "repo": repo_full, "path": path, "mode": "search"},
            )
        )
    return docs
