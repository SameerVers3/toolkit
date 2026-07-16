from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Mapping
from typing import Any

import httpx

from relay.config import Settings
from relay.providers.base import (
    Provider,
    ProviderRequest,
    ProviderResponse,
    ProviderStream,
    copy_forward_headers,
)
from relay.transform.anthropic_normalize import (
    normalize_anthropic_response,
    prepare_fireworks_request_body,
    rewrite_sse_chunk,
)

logger = logging.getLogger(__name__)


class _HttpxStream(ProviderStream):
    def __init__(
        self,
        response: httpx.Response,
        *,
        client_model: str | None,
        rewrite_model: bool,
    ) -> None:
        super().__init__(
            status_code=response.status_code,
            headers=_filter_response_headers(response.headers),
            media_type="text/event-stream",
        )
        self._response = response
        self._client_model = client_model
        self._rewrite_model = rewrite_model

    async def __aiter__(self) -> AsyncIterator[bytes]:
        try:
            async for chunk in self._response.aiter_bytes():
                if not chunk:
                    continue
                if self._rewrite_model and self._client_model:
                    yield rewrite_sse_chunk(
                        chunk,
                        client_model=self._client_model,
                        rewrite_model=True,
                    )
                else:
                    yield chunk
        finally:
            await self._response.aclose()


class FireworksProvider(Provider):
    name = "fireworks"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_url = settings.fireworks_base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(connect=30.0, read=600.0, write=60.0, pool=30.0),
            follow_redirects=False,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def _auth_headers(self, api_key: str, incoming: Mapping[str, str]) -> dict[str, str]:
        headers = copy_forward_headers(incoming)
        headers["authorization"] = f"Bearer {api_key}"
        headers.setdefault("content-type", "application/json")
        headers.setdefault("accept", "application/json")
        headers.pop("x-api-key", None)
        return headers

    async def create_message(
        self, request: ProviderRequest
    ) -> ProviderResponse | ProviderStream:
        body = prepare_fireworks_request_body(
            dict(request.body or {}),
            strip_extensions=self.settings.strip_provider_extensions,
        )
        if "model" not in body and request.client_model:
            body["model"] = request.client_model

        stream = bool(body.get("stream")) or request.stream
        headers = self._auth_headers(request.api_key, request.headers)
        if stream:
            headers["accept"] = "text/event-stream"

        if stream:
            req = self._client.build_request(
                "POST",
                "/v1/messages",
                json=body,
                headers=headers,
                params=request.query or None,
            )
            response = await self._client.send(req, stream=True)
            if response.status_code >= 400:
                error_body = await response.aread()
                await response.aclose()
                return self._error_response(
                    response.status_code, error_body, response.headers
                )

            return _HttpxStream(
                response,
                client_model=request.client_model,
                rewrite_model=self.settings.rewrite_response_model,
            )

        response = await self._client.post(
            "/v1/messages",
            json=body,
            headers=headers,
            params=request.query or None,
        )
        return self._json_response(
            response,
            client_model=request.client_model,
            rewrite_model=self.settings.rewrite_response_model,
        )

    async def count_tokens(self, request: ProviderRequest) -> ProviderResponse:
        body = prepare_fireworks_request_body(
            dict(request.body or {}),
            strip_extensions=self.settings.strip_provider_extensions,
        )
        headers = self._auth_headers(request.api_key, request.headers)
        response = await self._client.post(
            "/v1/messages/count_tokens",
            json=body,
            headers=headers,
        )
        if response.status_code == 404:
            return ProviderResponse(
                status_code=404,
                body={
                    "type": "error",
                    "error": {
                        "type": "not_found_error",
                        "message": "count_tokens is not available on this Fireworks endpoint",
                    },
                },
            )
        return self._json_response(response, client_model=None, rewrite_model=False)

    async def list_models(self, request: ProviderRequest) -> ProviderResponse:
        data: list[dict[str, Any]] = []
        seen: set[str] = set()

        for alias in self.settings.model_map:
            if not (alias.startswith("claude") or alias.startswith("anthropic")):
                continue
            if alias in seen:
                continue
            seen.add(alias)
            data.append(
                {
                    "type": "model",
                    "id": alias,
                    "display_name": alias,
                    "created_at": "1970-01-01T00:00:00Z",
                }
            )

        try:
            headers = self._auth_headers(request.api_key, request.headers)
            upstream = await self._client.get("/v1/models", headers=headers)
            if upstream.status_code == 200:
                payload = upstream.json()
                for item in payload.get("data") or []:
                    raw_id = item.get("id") or item.get("root")
                    if not raw_id or raw_id in seen:
                        continue
                    display = raw_id
                    for alias, target in self.settings.model_map.items():
                        if target == raw_id:
                            display = alias
                            break
                    if not (
                        display.startswith("claude") or display.startswith("anthropic")
                    ):
                        continue
                    seen.add(display)
                    data.append(
                        {
                            "type": "model",
                            "id": display,
                            "display_name": display,
                            "created_at": "1970-01-01T00:00:00Z",
                        }
                    )
        except Exception:
            logger.debug("Fireworks /v1/models probe failed", exc_info=True)

        return ProviderResponse(
            status_code=200,
            body={"data": data, "has_more": False},
        )

    def _json_response(
        self,
        response: httpx.Response,
        *,
        client_model: str | None,
        rewrite_model: bool,
    ) -> ProviderResponse:
        try:
            payload: Any = response.json()
        except Exception:
            return ProviderResponse(
                status_code=response.status_code,
                body=response.text,
                headers=_filter_response_headers(response.headers),
                media_type=response.headers.get("content-type", "application/json"),
            )

        if isinstance(payload, dict) and response.status_code < 400:
            payload = normalize_anthropic_response(
                payload,
                client_model=client_model,
                rewrite_model=rewrite_model,
            )

        return ProviderResponse(
            status_code=response.status_code,
            body=payload,
            headers=_filter_response_headers(response.headers),
        )

    def _error_response(
        self,
        status_code: int,
        body: bytes,
        headers: Mapping[str, str],
    ) -> ProviderResponse:
        try:
            payload: Any = json.loads(body)
        except Exception:
            payload = {
                "type": "error",
                "error": {
                    "type": "api_error",
                    "message": body.decode("utf-8", errors="replace"),
                },
            }
        return ProviderResponse(
            status_code=status_code,
            body=payload,
            headers=_filter_response_headers(headers),
        )


def _filter_response_headers(headers: Mapping[str, str]) -> dict[str, str]:
    skip = {
        "content-length",
        "transfer-encoding",
        "connection",
        "keep-alive",
        "content-encoding",
    }
    return {k: v for k, v in headers.items() if k.lower() not in skip}
