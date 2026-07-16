from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from relay.auth import require_api_key
from relay.config import Settings, get_settings
from relay.providers.base import Provider, ProviderRequest, ProviderResponse, ProviderStream

router = APIRouter(tags=["anthropic"])


def get_provider(request: Request) -> Provider:
    return request.app.state.provider


def get_fallback_key(settings: Settings = Depends(get_settings)) -> str | None:
    return settings.fireworks_api_key


@router.head("/")
async def connectivity_probe() -> Response:
    return Response(status_code=200)


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    return {
        "status": "ok",
        "provider": settings.provider,
        "version": getattr(request.app.state, "version", "0.1.0"),
    }


@router.post("/v1/messages")
@router.post("/v1/messages/")
async def create_message(
    request: Request,
    provider: Provider = Depends(get_provider),
    settings: Settings = Depends(get_settings),
    fallback_key: str | None = Depends(get_fallback_key),
) -> Response:
    api_key = require_api_key(request, fallback=fallback_key)
    body = await _read_json_body(request)

    client_model = body.get("model")
    try:
        resolved = settings.resolve_model(client_model)
    except ValueError as exc:
        return _anthropic_error(400, "invalid_request_error", str(exc))

    body = {**body, "model": resolved}
    original_model = client_model or resolved

    result = await provider.create_message(
        ProviderRequest(
            path="/v1/messages",
            method="POST",
            body=body,
            headers=dict(request.headers),
            query={k: v for k, v in request.query_params.multi_items()},
            api_key=api_key,
            client_model=original_model if settings.rewrite_response_model else resolved,
            stream=bool(body.get("stream")),
        )
    )
    return await _to_fastapi_response(result)


@router.post("/v1/messages/count_tokens")
@router.post("/v1/messages/count_tokens/")
async def count_tokens(
    request: Request,
    provider: Provider = Depends(get_provider),
    settings: Settings = Depends(get_settings),
    fallback_key: str | None = Depends(get_fallback_key),
) -> Response:
    api_key = require_api_key(request, fallback=fallback_key)
    body = await _read_json_body(request)

    client_model = body.get("model")
    try:
        resolved = settings.resolve_model(client_model)
    except ValueError as exc:
        return _anthropic_error(400, "invalid_request_error", str(exc))

    body = {**body, "model": resolved}
    result = await provider.count_tokens(
        ProviderRequest(
            path="/v1/messages/count_tokens",
            method="POST",
            body=body,
            headers=dict(request.headers),
            api_key=api_key,
            client_model=client_model,
        )
    )
    return await _to_fastapi_response(result)


@router.get("/v1/models")
async def list_models(
    request: Request,
    provider: Provider = Depends(get_provider),
    fallback_key: str | None = Depends(get_fallback_key),
) -> Response:
    api_key = require_api_key(request, fallback=fallback_key)
    result = await provider.list_models(
        ProviderRequest(
            path="/v1/models",
            method="GET",
            headers=dict(request.headers),
            query={k: v for k, v in request.query_params.multi_items()},
            api_key=api_key,
        )
    )
    return await _to_fastapi_response(result)


async def _read_json_body(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "type": "error",
                "error": {
                    "type": "invalid_request_error",
                    "message": f"Invalid JSON body: {exc}",
                },
            },
        ) from exc
    if not isinstance(body, dict):
        raise HTTPException(
            status_code=400,
            detail={
                "type": "error",
                "error": {
                    "type": "invalid_request_error",
                    "message": "Request body must be a JSON object",
                },
            },
        )
    return body


async def _to_fastapi_response(result: ProviderResponse | ProviderStream) -> Response:
    if isinstance(result, ProviderStream):

        async def event_source():
            async for chunk in result:
                yield chunk

        return StreamingResponse(
            event_source(),
            status_code=result.status_code,
            media_type=result.media_type,
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                **{
                    k: v
                    for k, v in result.headers.items()
                    if k.lower() not in {"content-type", "content-length"}
                },
            },
        )

    body = result.body
    if isinstance(body, (dict, list)):
        return JSONResponse(
            content=body,
            status_code=result.status_code,
            headers={
                k: v
                for k, v in result.headers.items()
                if k.lower() not in {"content-type", "content-length"}
            },
        )
    if isinstance(body, bytes):
        return Response(
            content=body,
            status_code=result.status_code,
            media_type=result.media_type,
        )
    return Response(
        content=str(body),
        status_code=result.status_code,
        media_type=result.media_type,
    )


def _anthropic_error(status: int, err_type: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "type": "error",
            "error": {"type": err_type, "message": message},
        },
    )
