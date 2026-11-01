"""Unit tests for external source connectors and ingest request validation."""

from __future__ import annotations

import base64
import json
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from opencrab.integrations import SOURCE_TYPES, SourceFetchError, fetch_source_documents
from opencrab.integrations.gdrive import fetch_gdrive_documents
from opencrab.integrations.github import fetch_github_documents
from opencrab.integrations.notion import fetch_notion_documents
from opencrab.integrations.obsidian import fetch_obsidian_documents


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        json_data: Any = None,
        text: str = "",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._json = json_data
        self.text = text if text or json_data is None else json.dumps(json_data)
        self.headers = headers or {}

    def json(self) -> Any:
        return self._json


def test_source_types_match_web_ui() -> None:
    assert set(SOURCE_TYPES) == {"obsidian", "notion", "gdrive", "github"}


def test_unsupported_source_type() -> None:
    with pytest.raises(SourceFetchError, match="Unsupported source_type"):
        fetch_source_documents("dropbox", access_token="tok")


def test_github_repo_readme_and_markdown() -> None:
    readme_body = base64.b64encode(b"# Hello repo").decode()
    md_body = base64.b64encode(b"note body").decode()

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/readme"):
            return httpx.Response(
                200,
                json={
                    "encoding": "base64",
                    "content": readme_body,
                    "path": "README.md",
                    "html_url": "https://github.com/acme/demo/blob/main/README.md",
                },
            )
        if path.endswith("/git/trees/HEAD"):
            return httpx.Response(
                200,
                json={
                    "tree": [
                        {"type": "blob", "path": "docs/guide.md"},
                        {"type": "blob", "path": "src/main.py"},
                    ]
                },
            )
        if path.endswith("/contents/docs/guide.md"):
            return httpx.Response(
                200,
                json={
                    "encoding": "base64",
                    "content": md_body,
                    "html_url": "https://github.com/acme/demo/blob/main/docs/guide.md",
                },
            )
        return httpx.Response(404, json={"message": "not found"})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport, base_url="https://api.github.com") as client:
        docs = fetch_github_documents(
            access_token="ghp_test",
            query="acme/demo",
            max_items=10,
            client=client,
        )

    assert len(docs) == 2
    assert docs[0].title == "acme/demo README"
    assert "Hello repo" in docs[0].text
    assert docs[1].metadata["path"] == "docs/guide.md"


def test_notion_search_and_blocks() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/search"):
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "object": "page",
                            "id": "11111111-1111-1111-1111-111111111111",
                            "url": "https://www.notion.so/Hello-11111111111111111111111111111111",
                            "properties": {
                                "Name": {
                                    "type": "title",
                                    "title": [{"plain_text": "Hello Page"}],
                                }
                            },
                        }
                    ]
                },
            )
        if "/blocks/" in request.url.path and request.url.path.endswith("/children"):
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "type": "paragraph",
                            "paragraph": {"rich_text": [{"plain_text": "Notion body"}]},
                        }
                    ],
                    "has_more": False,
                },
            )
        return httpx.Response(404, json={"message": "not found"})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport, base_url="https://api.notion.com") as client:
        docs = fetch_notion_documents(
            access_token="secret_test",
            query="Hello",
            max_items=5,
            client=client,
        )

    assert len(docs) == 1
    assert docs[0].title == "Hello Page"
    assert "Notion body" in docs[0].text


def test_gdrive_export_document() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/files") and "alt" not in str(request.url):
            return httpx.Response(
                200,
                json={
                    "files": [
                        {
                            "id": "file123",
                            "name": "Strategy Doc",
                            "mimeType": "application/vnd.google-apps.document",
                            "webViewLink": "https://docs.google.com/document/d/file123",
                        }
                    ]
                },
            )
        if request.url.path.endswith("/files/file123") and "fields" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "id": "file123",
                    "name": "Strategy Doc",
                    "mimeType": "application/vnd.google-apps.document",
                    "webViewLink": "https://docs.google.com/document/d/file123",
                },
            )
        if request.url.path.endswith("/files/file123/export"):
            return httpx.Response(200, text="Exported drive text")
        return httpx.Response(404, text="missing")

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport, base_url="https://www.googleapis.com") as client:
        docs = fetch_gdrive_documents(
            access_token="ya29.test",
            query="strategy",
            max_items=5,
            client=client,
        )

    assert len(docs) == 1
    assert docs[0].title == "Strategy Doc"
    assert "Exported drive text" in docs[0].text


def test_obsidian_search_notes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/search/simple/"):
            return httpx.Response(200, json=[{"filename": "Notes/Alpha.md"}])
        if request.url.path.endswith("/vault/Notes/Alpha.md"):
            return httpx.Response(
                200,
                text="# Alpha\n\nvault note",
                headers={"content-type": "text/markdown"},
            )
        return httpx.Response(404, text="missing")

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport, base_url="http://127.0.0.1:27123") as client:
        docs = fetch_obsidian_documents(
            access_token="obsidian-key",
            query="Alpha",
            max_items=5,
            client=client,
        )

    assert len(docs) == 1
    assert docs[0].title == "Alpha.md"
    assert "vault note" in docs[0].text


def test_ingest_request_accepts_source_payload() -> None:
    from apps.api.main import IngestRequest

    payload = IngestRequest(
        source_type="github",
        access_token="token",
        query="acme/demo",
        max_items=3,
    )
    assert payload.source_type == "github"
    assert payload.text is None


def test_ingest_request_requires_text_or_source() -> None:
    from apps.api.main import IngestRequest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        IngestRequest(metadata={"x": 1})


def test_api_source_ingest_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    from apps.api import main as api_main
    from opencrab.integrations.base import SourceDocument

    docs = [
        SourceDocument(
            external_id="github:acme/demo:readme",
            title="README",
            text="# Demo",
            url="https://example.com",
            metadata={"source": "github"},
        )
    ]

    monkeypatch.setattr(api_main, "fetch_source_documents", lambda *a, **k: docs)

    fake_hybrid = MagicMock()
    fake_hybrid.ingest.return_value = {"source_id": "s1", "stores": {"chromadb": "ok"}, "vector_id": "v1"}
    fake_docs = MagicMock()
    fake_docs.available = True
    fake_docs.upsert_source.return_value = "s1"
    fake_docs.list_sources.return_value = []
    fake_ctx = api_main.ApiContext(
        settings=MagicMock(storage_mode="local"),
        graph=MagicMock(available=False),
        vector=MagicMock(available=True),
        docs=fake_docs,
        sql=MagicMock(available=False),
        hybrid=fake_hybrid,
        impact=MagicMock(),
    )

    monkeypatch.setattr(api_main, "get_context", lambda: fake_ctx)
    monkeypatch.setattr(api_main, "_meter_call", lambda *a, **k: None)
    monkeypatch.setattr(api_main, "_enforce_ingest_limits", lambda *a, **k: None)
    monkeypatch.setattr(api_main, "_count_user_sources", lambda *a, **k: 0)

    payload = api_main.IngestRequest(
        source_type="github",
        access_token="tok",
        query="acme/demo",
    )
    auth = api_main.AuthContext(user_id="user-1", tier="pro")
    result = api_main.ingest_text(payload, auth=auth, ctx=fake_ctx)

    assert result["ok"] is True
    assert result["mode"] == "source"
    assert result["ingested"] == 1
    assert result["items"][0]["title"] == "README"
    fake_hybrid.ingest.assert_called_once()
