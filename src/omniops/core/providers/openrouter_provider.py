"""OpenRouter provider (OpenAI-compatible with extra_headers)"""
import asyncio
import logging
import os
import time
from typing import Any, Dict, Optional

import httpx

from omniops.core.providers import BaseProvider, ProviderConfig, register

logger = logging.getLogger(__name__)
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def _get_proxy() -> Optional[str]:
    return os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")


def _extract_retry_after(headers: httpx.Headers) -> float:
    """Parse Retry-After header (supports seconds or HTTP date)"""
    val = headers.get("retry-after", "")
    try:
        return float(val)
    except ValueError:
        return 5.0


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
        t0 = time.monotonic()
        messages: list = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user_message})

        extra_body: Dict[str, Any] = {}
        if json_mode:
            extra_body["response_format"] = {"type": "json_object"}

        logger.info(f"[OpenRouter] calling model={self.config.model}, json_mode={json_mode}, "
                    f"max_tokens={self.config.max_tokens}, temp={temperature}, msg_len={len(user_message)}")

        request_body = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": self.config.max_tokens,
            **extra_body,
        }

        response = await self._call_with_retry(request_body, json_mode=json_mode)

        response.raise_for_status()
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        data = response.json()
        msg = data["choices"][0]["message"]
        content = msg.get("content") or msg.get("reasoning") or ""
        usage = data.get("usage", {})
        tokens = usage.get("total_tokens", 0)
        logger.info(f"[OpenRouter] response in {elapsed_ms}ms, tokens={tokens}, content_len={len(content)}, "
                    f"first_200={content[:200]!r}")
        return content

    async def _call_with_retry(
        self,
        request_body: Dict[str, Any],
        json_mode: bool,
        max_retries: int = 3,
    ) -> httpx.Response:
        """Execute request with retry + exponential backoff on 429/500/502/503/504."""
        last_exc: Optional[Exception] = None
        last_response: Optional[httpx.Response] = None

        for attempt in range(max_retries):
            response: Optional[httpx.Response] = None
            exc: Optional[Exception] = None
            try:
                response = await self._client.post(
                    f"{self._base_url}/chat/completions",
                    json=request_body,
                    timeout=httpx.Timeout(self.config.timeout, connect=10.0),
                )
            except httpx.HTTPStatusError as e:
                response = e.response
                exc = e
            except Exception as e:
                exc = e

            status = response.status_code if response else None

            # 400 with response_format → strip and retry immediately
            if status == 400 and json_mode and "response_format" in request_body:
                logger.warning("[OpenRouter] 400 with response_format, retrying without it")
                request_body = {k: v for k, v in request_body.items() if k != "response_format"}
                continue

            # Retryable: 429 rate-limit, 5xx server errors
            if status in (429, 500, 502, 503, 504):
                retry_after = _extract_retry_after(response.headers) if response else 5.0
                wait = retry_after * (2 ** attempt)
                logger.warning(f"[OpenRouter] attempt {attempt+1}/{max_retries} got {status}, "
                               f"retrying in {wait:.1f}s (Retry-After={retry_after:.1f})")
                await asyncio.sleep(wait)
                continue

            if exc:
                last_exc = exc
                continue

            # On success or non-retryable status, return the response
            return response

        # Exhausted retries
        if last_exc:
            raise last_exc
        return response  # response may be the last 429/5xx

    async def close(self) -> None:
        await self._client.aclose()