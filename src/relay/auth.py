from __future__ import annotations

from fastapi import HTTPException, Request, status


def extract_api_key(request: Request) -> str | None:
    authorization = request.headers.get("authorization")
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token.strip():
            return token.strip()
        if not _ and authorization.strip():
            return authorization.strip()

    x_api_key = request.headers.get("x-api-key")
    if x_api_key and x_api_key.strip():
        return x_api_key.strip()

    return None


def require_api_key(request: Request, *, fallback: str | None = None) -> str:
    key = extract_api_key(request)
    if key:
        return key
    if fallback:
        return fallback
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "type": "error",
            "error": {
                "type": "authentication_error",
                "message": (
                    "Missing API key. Set ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN "
                    "on the client, or FIREWORKS_API_KEY on the relay."
                ),
            },
        },
    )
