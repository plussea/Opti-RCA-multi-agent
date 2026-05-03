"""LLM Provider Registry — OmniOps

默认使用 OpenRouter（.env 中 LLM_PROVIDER=openrouter）。
所有 Agent 通过 `get_provider()` 获取 LLM 实例。
"""
from functools import lru_cache
from typing import Any, Dict, Optional, Type

from omniops.core.providers.base import BaseProvider, ProviderConfig

# Global registry: provider_name -> provider class
_REGISTRY: Dict[str, Type[BaseProvider]] = {}

# Cached instances
_cache: Dict[str, BaseProvider] = {}


def register(name: str) -> callable:
    """Decorator: register a provider class under `name`"""
    def decorator(cls: Type[BaseProvider]) -> Type[BaseProvider]:
        _REGISTRY[name] = cls
        return cls
    return decorator


def get_provider(name: Optional[str] = None) -> BaseProvider:
    """Factory: return a provider instance by name (default from settings).

    Instances are cached per name — safe to call repeatedly.
    """
    if name is None:
        name = default_provider_name()

    if name not in _cache:
        if name not in _REGISTRY:
            available = ", ".join(sorted(_REGISTRY.keys())) or "none"
            raise ValueError(
                f"Unknown provider '{name}'. Available: {available}. "
                "Check LLM_PROVIDER in .env (currently configured for openrouter)."
            )
        _cache[name] = _build_provider(name)

    return _cache[name]


def default_provider_name() -> str:
    """Read the default provider from settings (lazy import to avoid cycle)"""
    from omniops.core.config import get_settings
    settings = get_settings()
    return settings.llm_provider  # defaults to "openrouter"


def _build_provider(name: str) -> BaseProvider:
    """Build a ProviderConfig + provider instance from settings"""
    from omniops.core.config import get_settings
    settings = get_settings()

    if name == "openrouter":
        return _build_openrouter(settings)
    else:
        raise ValueError(f"Unknown provider: {name}. Only 'openrouter' is configured.")


def _build_openrouter(settings: Any) -> BaseProvider:
    """Build OpenRouter provider (OpenAI-compatible API)"""
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"[Provider] building OpenRouter: model={settings.llm_model}, "
                 f"max_tokens={settings.anthropic_max_tokens}, api_key_set={bool(settings.openrouter_api_key)}")
    from omniops.core.providers.openrouter_provider import OpenRouterProvider

    config = ProviderConfig(
        api_key=settings.openrouter_api_key,
        base_url="https://openrouter.ai/api/v1",
        model=settings.llm_model,  # LLM_MODEL from .env
        max_tokens=settings.anthropic_max_tokens,
        timeout=60.0,
    )
    return OpenRouterProvider(config)


# Register the OpenRouter provider
from omniops.core.providers.openrouter_provider import OpenRouterProvider  # noqa: E402
register("openrouter")(OpenRouterProvider)

__all__ = [
    "BaseProvider",
    "ProviderConfig",
    "get_provider",
    "register",
    "default_provider_name",
]
