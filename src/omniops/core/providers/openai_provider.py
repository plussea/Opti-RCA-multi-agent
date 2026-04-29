"""OpenAI-compatible provider (uses openai SDK)"""
from omniops.core.providers import BaseProvider, ProviderConfig, register

try:
    from openai import AsyncOpenAI
except ImportError:  # pragma: no cover
    AsyncOpenAI = None  # type: ignore


@register("openai")
class OpenAIProvider(BaseProvider):
    """OpenAI provider using the official AsyncOpenAI client"""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        if AsyncOpenAI is None:  # pragma: no cover
            raise ImportError("openai package not installed. Run: pip install openai")
        import httpx
        self._client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url or None,
            timeout=httpx.Timeout(config.timeout),
            http_client=None,
        )

    async def _do_request(
        self,
        system: str,
        user_message: str,
        temperature: float,
        json_mode: bool,
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user_message})

        extra_body: Dict[str, Any] = {}
        if json_mode:
            extra_body["response_format"] = {"type": "json_object"}

        response = await self._client.chat.completions.create(
            model=self.config.model,
            messages=messages,  # type: ignore
            temperature=temperature,
            max_tokens=self.config.max_tokens,
            extra_body=extra_body if extra_body else None,
        )
        return response.choices[0].message.content or ""
