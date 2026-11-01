"""Shared types for external source connectors."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SourceDocument:
    """A single document harvested from an external source."""

    external_id: str
    title: str
    text: str
    url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class SourceFetchError(RuntimeError):
    """Raised when an upstream source API rejects or fails a request."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
