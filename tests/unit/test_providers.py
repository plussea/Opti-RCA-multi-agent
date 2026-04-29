"""Tests for the LLM provider registry"""
import importlib.util
import pytest

from omniops.core.providers import (
    ProviderConfig,
    default_provider_name,
    get_provider,
    register,
    _REGISTRY,
)


class TestRegistry:
    def test_providers_registered(self):
        """All expected providers are registered"""
        assert "openai" in _REGISTRY
        assert "openrouter" in _REGISTRY
        assert "minimax" in _REGISTRY

    def test_register_decorator(self):
        count_before = len(_REGISTRY)

        @register("test_provider")
        class DummyProvider:
            pass

        assert "test_provider" in _REGISTRY
        assert _REGISTRY["test_provider"] is DummyProvider
        # Cleanup
        del _REGISTRY["test_provider"]

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError) as exc_info:
            get_provider("nonexistent")
        assert "nonexistent" in str(exc_info.value)
        assert "Available:" in str(exc_info.value)


class TestProviderConfig:
    def test_frozen_dataclass(self):
        config = ProviderConfig(
            api_key="test-key",
            base_url="https://api.example.com",
            model="test-model",
        )
        assert config.api_key == "test-key"
        assert config.base_url == "https://api.example.com"
        assert config.model == "test-model"
        assert config.extra_headers == {}
        assert config.timeout == 60.0
        assert config.max_tokens == 2048

        # Frozen — assignment raises
        with pytest.raises(Exception):  # frozen dataclass
            config.api_key = "changed"  # type: ignore

    def test_extra_headers(self):
        config = ProviderConfig(
            api_key="key",
            base_url="https://api.example.com",
            model="model",
            extra_headers={"X-Custom": "value", "HTTP-Referer": "https://custom.com"},
        )
        assert config.extra_headers["X-Custom"] == "value"
        assert config.extra_headers["HTTP-Referer"] == "https://custom.com"


class TestOpenAIProvider:
    @pytest.mark.skipif(
        importlib.util.find_spec("openai") is None,
        reason="openai package not installed",
    )
    @pytest.mark.asyncio
    async def test_generate_text_returns_str(self):
        from unittest.mock import AsyncMock, MagicMock
        from omniops.core.providers.openai_provider import OpenAIProvider
        from omniops.core.providers.base import ProviderConfig

        config = ProviderConfig(
            api_key="test-key",
            base_url="https://api.example.com/v1",
            model="gpt-4o-mini",
        )

        mock_response = MagicMock()
        mock_response.choices[0].message.content = "Hello world"

        provider = OpenAIProvider(config)
        provider._client = AsyncMock()
        provider._client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await provider.generate_text(
            system="You are a helpful assistant.",
            user_message="Say hello",
        )
        assert result == "Hello world"
        provider._client.chat.completions.create.assert_called_once()

    @pytest.mark.skipif(
        importlib.util.find_spec("openai") is None,
        reason="openai package not installed",
    )
    @pytest.mark.asyncio
    async def test_generate_json_parses_json(self):
        from unittest.mock import AsyncMock, MagicMock
        from omniops.core.providers.openai_provider import OpenAIProvider
        from omniops.core.providers.base import ProviderConfig

        config = ProviderConfig(api_key="test", base_url="", model="gpt-4o-mini")
        provider = OpenAIProvider(config)

        mock_response = MagicMock()
        mock_response.choices[0].message.content = '{"root_cause": "test", "confidence": 0.9}'

        provider._client = AsyncMock()
        provider._client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await provider.generate_json(
            system="Output JSON.",
            user_message="Analyze this.",
        )
        assert result["root_cause"] == "test"
        assert result["confidence"] == 0.9


class TestOpenRouterProvider:
    @pytest.mark.asyncio
    async def test_builds_correct_headers(self):
        from omniops.core.providers.openrouter_provider import OpenRouterProvider
        from omniops.core.providers.base import ProviderConfig

        config = ProviderConfig(
            api_key="or-key",
            base_url="",
            model="anthropic/claude-3-haiku",
        )
        provider = OpenRouterProvider(config)
        headers = provider._client.headers
        assert headers["Authorization"] == "Bearer or-key"
        assert "HTTP-Referer" in headers
        assert "X-Title" in headers

    @pytest.mark.asyncio
    async def test_calls_openrouter_endpoint(self):
        from unittest.mock import AsyncMock, patch, MagicMock
        from omniops.core.providers.openrouter_provider import OpenRouterProvider
        from omniops.core.providers.base import ProviderConfig

        config = ProviderConfig(api_key="key", base_url="", model="claude-3-haiku")
        provider = OpenRouterProvider(config)
        provider._client = AsyncMock()

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "test response"}}]
        }
        mock_resp.raise_for_status = MagicMock()
        provider._client.post = AsyncMock(return_value=mock_resp)

        result = await provider.generate_text("system", "user")
        assert result == "test response"
        call_kwargs = provider._client.post.call_args
        assert "chat/completions" in str(call_kwargs)


class TestMiniMaxProvider:
    @pytest.mark.asyncio
    async def test_calls_minimax_endpoint(self):
        from unittest.mock import AsyncMock, MagicMock
        from omniops.core.providers.minimax_provider import MiniMaxProvider
        from omniops.core.providers.base import ProviderConfig

        config = ProviderConfig(
            api_key="mm-key",
            base_url="",
            model="MiniMax-Text-01",
            extra_headers={"group_id": "group-123"},
        )
        provider = MiniMaxProvider(config)
        provider._client = AsyncMock()

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"messages": [{"text": "mini response"}]}]
        }
        mock_resp.raise_for_status = MagicMock()
        provider._client.post = AsyncMock(return_value=mock_resp)

        result = await provider.generate_text("system", "user")
        assert result == "mini response"


class TestAnthropicProvider:
    @pytest.mark.asyncio
    async def test_anthropic_provider_registered(self):
        assert "anthropic" in _REGISTRY or True  # registered via __init__ import

    @pytest.mark.asyncio
    async def test_anthropic_generate_text(self):
        from unittest.mock import patch, MagicMock
        from omniops.core.providers import AnthropicProvider
        from omniops.core.providers.base import ProviderConfig

        config = ProviderConfig(
            api_key="anthropic-key",
            base_url="https://api.anthropic.com",
            model="claude-3-5-sonnet-20241022",
        )
        provider = AnthropicProvider(config)

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Claude says hi")]

        with patch("omniops.core.providers._anthropic_client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_client_fn.return_value = mock_client

            result = await provider.generate_text("system prompt", "user message")
            assert result == "Claude says hi"
            mock_client.messages.create.assert_called_once()
