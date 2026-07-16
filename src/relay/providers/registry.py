from __future__ import annotations

from relay.config import Settings
from relay.providers.base import Provider
from relay.providers.fireworks import FireworksProvider

_REGISTRY: dict[str, type[Provider]] = {
    "fireworks": FireworksProvider,
}


def register_provider(name: str, cls: type[Provider]) -> None:
    _REGISTRY[name.lower()] = cls


def available_providers() -> list[str]:
    return sorted(_REGISTRY)


def create_provider(settings: Settings) -> Provider:
    name = settings.provider.lower().strip()
    try:
        cls = _REGISTRY[name]
    except KeyError as exc:
        known = ", ".join(available_providers()) or "(none)"
        raise ValueError(f"Unknown RELAY_PROVIDER '{name}'. Known: {known}") from exc
    return cls(settings)
