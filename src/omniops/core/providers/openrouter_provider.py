"""OpenRouter provider (OpenAI-compatible with extra_headers)"""
import os
from typing import Any, Dict, Optional

import httpx

from omniops.core.providers import BaseProvider, ProviderConfig, register

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def _get_proxy() -> Optional[str]:
    return os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")


@register("openrouter")
class OpenRouterProvider(BaseProvider):
    """OpenRouter provider — OpenAI-compatible with referrer/title headers"""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._base_url = (config.base_url or OPENROUTER_BASE_URL).rstrip("/")
        proxy = _get_proxy()
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(config.timeout),
            headers=self._build_headers(config),
            proxy=proxy,
        )

    def _build_headers(self, config: ProviderConfig) -> Dict[str, str]:
        headers: Dict[str, str] = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        }
        # OpenRouter requires these
        if "HTTP-Referer" not in config.extra_headers:
            headers["HTTP-Referer"] = "https://omniops.ai"
        if "X-Title" not in config.extra_headers:
            headers["X-Title"] = "OmniOps"
        headers.update(config.extra_headers)
        return headers

    async def _do_request(
        self,
        system: str,
        user_message: str,
        temperature: float,
        json_mode: bool,
    ) -> str:
        messages: list = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user_message})

        extra_body: Dict[str, Any] = {}
        if json_mode:
            extra_body["response_format"] = {"type": "json_object"}

        response = await self._client.post(
            f"{self._base_url}/chat/completions",
            json={
                "model": self.config.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": self.config.max_tokens,
                **extra_body,
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"] or ""

    async def close(self) -> None:
        await self._client.aclose()
