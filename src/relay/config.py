from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_model_map(value: Any) -> dict[str, str]:
    if value is None or value == "":
        return {}
    if isinstance(value, dict):
        return {str(k): str(v) for k, v in value.items()}
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        if text.startswith("{"):
            import json

            data = json.loads(text)
            if not isinstance(data, dict):
                raise ValueError("MODEL_MAP JSON must be an object")
            return {str(k): str(v) for k, v in data.items()}
        mapping: dict[str, str] = {}
        for part in text.split(","):
            part = part.strip()
            if not part:
                continue
            if "=" not in part:
                raise ValueError(
                    f"Invalid MODEL_MAP entry '{part}'; expected alias=model"
                )
            alias, model = part.split("=", 1)
            mapping[alias.strip()] = model.strip()
        return mapping
    raise ValueError("MODEL_MAP must be a dict, JSON object, or alias=model list")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = Field(default="127.0.0.1", alias="RELAY_HOST")
    port: int = Field(default=8080, alias="RELAY_PORT")
    log_level: str = Field(default="info", alias="RELAY_LOG_LEVEL")
    provider: str = Field(default="fireworks", alias="RELAY_PROVIDER")
    fireworks_api_key: str | None = Field(default=None, alias="FIREWORKS_API_KEY")
    fireworks_base_url: str = Field(
        default="https://api.fireworks.ai/inference",
        alias="FIREWORKS_BASE_URL",
    )
    default_model: str | None = Field(default=None, alias="RELAY_DEFAULT_MODEL")
    model_map: dict[str, str] = Field(default_factory=dict, alias="MODEL_MAP")
    rewrite_response_model: bool = Field(
        default=True, alias="RELAY_REWRITE_RESPONSE_MODEL"
    )
    strip_provider_extensions: bool = Field(
        default=True, alias="RELAY_STRIP_PROVIDER_EXTENSIONS"
    )

    @field_validator("model_map", mode="before")
    @classmethod
    def validate_model_map(cls, value: Any) -> dict[str, str]:
        return _parse_model_map(value)

    def resolve_model(self, requested: str | None) -> str:
        if not requested:
            if self.default_model:
                return self.default_model
            raise ValueError("No model provided and RELAY_DEFAULT_MODEL is unset")

        if requested in self.model_map:
            return self.model_map[requested]

        lower = requested.lower()
        for alias, target in self.model_map.items():
            if alias.lower() == lower:
                return target

        return requested


@lru_cache
def get_settings() -> Settings:
    return Settings()
