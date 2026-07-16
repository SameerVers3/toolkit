from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from relay import __version__
from relay.config import Settings, get_settings
from relay.harnesses import anthropic as anthropic_harness
from relay.providers.registry import create_provider

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        provider = create_provider(settings)
        app.state.provider = provider
        app.state.settings = settings
        app.state.version = __version__
        logger.info(
            "Relay ready provider=%s base=%s",
            settings.provider,
            getattr(settings, "fireworks_base_url", ""),
        )
        try:
            yield
        finally:
            await provider.aclose()

    app = FastAPI(
        title="Anthropic Relay",
        version=__version__,
        lifespan=lifespan,
    )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        detail = exc.detail
        if isinstance(detail, dict) and detail.get("type") == "error":
            return JSONResponse(status_code=exc.status_code, content=detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "type": "error",
                "error": {
                    "type": "api_error",
                    "message": detail if isinstance(detail, str) else str(detail),
                },
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "type": "error",
                "error": {
                    "type": "invalid_request_error",
                    "message": json_safe_validation(exc),
                },
            },
        )

    app.include_router(anthropic_harness.router)
    return app


def json_safe_validation(exc: RequestValidationError) -> str:
    try:
        return "; ".join(
            f"{'.'.join(str(p) for p in err.get('loc', ()))}: {err.get('msg')}"
            for err in exc.errors()
        )
    except Exception:
        return str(exc)


app = create_app()


def run() -> None:
    import uvicorn

    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())
    uvicorn.run(
        "relay.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
        reload=False,
    )


if __name__ == "__main__":
    run()
