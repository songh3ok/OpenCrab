"""External source connectors for ontology ingestion."""

from __future__ import annotations

from opencrab.integrations.base import SourceDocument, SourceFetchError
from opencrab.integrations.registry import SOURCE_TYPES, fetch_source_documents

__all__ = [
    "SOURCE_TYPES",
    "SourceDocument",
    "SourceFetchError",
    "fetch_source_documents",
]
