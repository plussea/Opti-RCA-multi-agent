"""LLM Provider Registry

Usage:
    from omniops.core.providers import get_provider

    provider = get_provider()  # uses default from config
    result = await provider.generate_json(system="...", user_message="...")
"""
from functools import lru_cache
from typing import Any, Callable, Dict, Optional, Type

from omniops.core.providers.base import BaseProvider, ProviderConfig

# Global registry: provider_name -> provider class
_REGISTRY: Dict[str, Type[BaseProvider]] = {}

# Cached instances
_cache: Dict[str, BaseProvider] = {}


def register(name: str) -> Callable[[Type[BaseProvider]], Type[BaseProvider]]:
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
                "Did you forget to install the provider package?"
            )
        _cache[name] = _build_provider(name)

    return _cache[name]


def default_provider_name() -> str:
    """Read the default provider from settings (lazy import to avoid cycle)"""
    from omniops.core.config import get_settings
    settings = get_settings()
    return settings.llm_provider


def _build_provider(name: str) -> BaseProvider:
    """Build a ProviderConfig + provider instance from settings"""
    from omniops.core.config import get_settings
    settings = get_settings()

    if name == "anthropic":
        return _build_anthropic(settings)
    elif name == "openai":
        return _build_openai(settings)
    elif name == "openrouter":
        return _build_openrouter(settings)
    elif name == "minimax":
        return _build_minimax(settings)
    else:
        raise ValueError(f"Cannot build unknown provider: {name}")


def _build_anthropic(settings: Any) -> BaseProvider:
    """Build Anthropic provider (uses official SDK)"""
    try:
        import anthropic  # noqa: F401
    except ImportError:
        raise ImportError("anthropic package not installed. Run: pip install anthropic") from None

    from omniops.core.providers.base import ProviderConfig

    # We use httpx for Anthropic too (simpler unified approach)
    # But we keep a separate import path so the SDK works
    config = ProviderConfig(
        api_key=settings.anthropic_api_key,
        base_url="https://api.anthropic.com",
        model=settings.anthropic_model,
        max_tokens=settings.anthropic_max_tokens,
        timeout=60.0,
        temperature=0.3,
    )
    return AnthropicProvider(config)


@lru_cache
def _anthropic_client() -> Any:
    import anthropic

    from omniops.core.config import get_settings
    settings = get_settings()
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


class AnthropicProvider(BaseProvider):
    """Anthropic Claude provider via the official SDK"""

    async def _do_request(
        self,
        system: str,
        user_message: str,
        temperature: float,
        json_mode: bool,
    ) -> str:
        system_text = system
        if json_mode:
            system_text = system + "\n\n请以 JSON 格式输出你的回答。"

        client = _anthropic_client()
        response = client.messages.create(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            system=system_text,
            messages=[{"role": "user", "content": user_message}],
            temperature=temperature,
        )
        return str(response.content[0].text)


def _build_openai(settings: Any) -> BaseProvider:
    from omniops.core.providers.base import ProviderConfig
    from omniops.core.providers.openai_provider import OpenAIProvider

    config = ProviderConfig(
        api_key=settings.openai_api_key,
        base_url="",
        model=settings.openai_model,
        max_tokens=settings.anthropic_max_tokens,
        timeout=60.0,
    )
    return OpenAIProvider(config)


def _build_openrouter(settings: Any) -> BaseProvider:
    from omniops.core.providers.base import ProviderConfig
    from omniops.core.providers.openrouter_provider import OpenRouterProvider

    config = ProviderConfig(
        api_key=settings.openrouter_api_key,
        base_url="https://openrouter.ai/api/v1",
        model=settings.llm_model,
        max_tokens=settings.anthropic_max_tokens,
        timeout=60.0,
    )
    return OpenRouterProvider(config)


def _build_minimax(settings: Any) -> BaseProvider:
    from omniops.core.providers.base import ProviderConfig
    from omniops.core.providers.minimax_provider import MiniMaxProvider

    config = ProviderConfig(
        api_key=settings.minimax_api_key,
        base_url="https://api.minimax.chat/v1",
        model=settings.minimax_model,
        max_tokens=settings.anthropic_max_tokens,
        timeout=60.0,
        extra_headers={"group_id": settings.minimax_group_id},
    )
    return MiniMaxProvider(config)


# Import all providers to trigger @register decorators
from omniops.core.providers import (  # noqa: E402
    minimax_provider,  # noqa: F401
    openai_provider,  # noqa: F401
    openrouter_provider,  # noqa: F401
)

__all__ = [
    "BaseProvider",
    "ProviderConfig",
    "get_provider",
    "register",
    "default_provider_name",
]
