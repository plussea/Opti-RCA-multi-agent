"""MiniMax provider (httpx-based, MiniMax-specific endpoint)"""
from typing import Any, Dict

import httpx

from omniops.core.providers import BaseProvider, ProviderConfig, register

MINIMAX_BASE_URL = "https://api.minimax.chat/v1"


@register("minimax")
class MiniMaxProvider(BaseProvider):
    """MiniMax provider — uses /text/chatcompletion_v2 endpoint"""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._base_url = (config.base_url or MINIMAX_BASE_URL).rstrip("/")
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(config.timeout),
        )

    async def _do_request(
        self,
        system: str,
        user_message: str,
        temperature: float,
        json_mode: bool,
    ) -> str:
        # Build messages — MiniMax uses "model_alias" for model selection
        messages: list = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user_message})

        # MiniMax uses group_id in URL path, api_key in header
        group_id = self.config.extra_headers.get("group_id", "")
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        # Remove group_id from extra_headers — it's part of the URL
        extra = {k: v for k, v in self.config.extra_headers.items() if k != "group_id"}
        headers.update(extra)

        payload: Dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
            "tokens_to_generate": self.config.max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        url = (
            f"{self._base_url}/text/chatcompletion_v2"
            if group_id
            else f"{self._base_url}/text/chatcompletion_v2?GroupId={group_id}"
        )
        # Actually, MiniMax uses GroupId query param
        url = f"{self._base_url}/text/chatcompletion_v2?GroupId={group_id}"

        response = await self._client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        # MiniMax returns: { ..., "choices": [{ "messages": [...] }] }
        choices = data.get("choices", [])
        if choices:
            msg = choices[0].get("messages", [{}])[-1]
            return str(msg.get("text", ""))
        return ""

    async def close(self) -> None:
        await self._client.aclose()
