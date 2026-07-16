from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProviderRequest:
    path: str
    method: str = "POST"
    body: dict[str, Any] | None = None
    headers: dict[str, str] = field(default_factory=dict)
    query: dict[str, str] = field(default_factory=dict)
    api_key: str = ""
    client_model: str | None = None
    stream: bool = False


@dataclass
class ProviderResponse:
    status_code: int
    body: dict[str, Any] | bytes | str
    headers: dict[str, str] = field(default_factory=dict)
    media_type: str = "application/json"


@dataclass
class ProviderStream:
    status_code: int
    headers: dict[str, str] = field(default_factory=dict)
    media_type: str = "text/event-stream"

    async def __aiter__(self) -> AsyncIterator[bytes]:
        raise NotImplementedError


class Provider(ABC):
    name: str

    @abstractmethod
    async def create_message(
        self, request: ProviderRequest
    ) -> ProviderResponse | ProviderStream: ...

    async def count_tokens(self, request: ProviderRequest) -> ProviderResponse:
        return ProviderResponse(
            status_code=501,
            body={
                "type": "error",
                "error": {
                    "type": "not_implemented_error",
                    "message": f"Provider '{self.name}' does not support count_tokens",
                },
            },
        )

    async def list_models(self, request: ProviderRequest) -> ProviderResponse:
        return ProviderResponse(
            status_code=501,
            body={
                "type": "error",
                "error": {
                    "type": "not_implemented_error",
                    "message": f"Provider '{self.name}' does not support list_models",
                },
            },
        )

    async def aclose(self) -> None:
        return None


def copy_forward_headers(headers: Mapping[str, str]) -> dict[str, str]:
    allow = {
        "anthropic-version",
        "anthropic-beta",
        "content-type",
        "accept",
        "user-agent",
        "x-claude-code-session-id",
        "x-claude-code-agent-id",
        "x-claude-code-parent-agent-id",
    }
    out: dict[str, str] = {}
    for key, value in headers.items():
        lower = key.lower()
        if (
            lower in allow
            or lower.startswith("anthropic-")
            or lower.startswith("x-claude-code-")
        ):
            out[lower] = value
    return out
