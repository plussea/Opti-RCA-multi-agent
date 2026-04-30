"""Provider base types"""
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass(frozen=True)
class ProviderConfig:
    """Provider configuration (immutable)"""
    api_key: str
    base_url: str
    model: str
    extra_headers: Dict[str, str] = field(default_factory=dict)
    timeout: float = 60.0
    max_tokens: int = 2048
    temperature: float = 0.3


class LLMProvider:
    """Protocol: any LLM provider must implement these methods"""

    async def generate_text(
        self,
        system: str,
        user_message: str,
        temperature: float = 0.7,
    ) -> str:
        raise NotImplementedError

    async def generate_json(
        self,
        system: str,
        user_message: str,
        temperature: float = 0.3,
    ) -> Dict[str, Any]:
        raise NotImplementedError


class BaseProvider(ABC):
    """Abstract base for all LLM providers"""

    def __init__(self, config: ProviderConfig):
        self.config = config

    async def generate_text(
        self,
        system: str,
        user_message: str,
        temperature: float = 0.7,
    ) -> str:
        """Generate plain text via _do_request hook"""
        content = await self._do_request(
            system=system,
            user_message=user_message,
            temperature=temperature,
            json_mode=False,
        )
        return content

    async def generate_json(
        self,
        system: str,
        user_message: str,
        temperature: float = 0.3,
    ) -> Dict[str, Any]:
        """Generate JSON-structured response"""
        content = await self._do_request(
            system=system,
            user_message=user_message,
            temperature=temperature,
            json_mode=True,
        )
        return self._parse_json(content)

    def _parse_json(self, content: str) -> Dict[str, Any]:
        """Parse JSON from model response text"""
        try:
            return dict(json.loads(content))
        except json.JSONDecodeError:
            # Try markdown code block
            match = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL)
            if match:
                return dict(json.loads(match.group(1)))
            # Try curly braces
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                return dict(json.loads(match.group(0)))
            raise ValueError(f"Failed to parse JSON from response: {content}") from None

    @abstractmethod
    async def _do_request(
        self,
        system: str,
        user_message: str,
        temperature: float,
        json_mode: bool,
    ) -> str:
        """Subclasses implement the actual HTTP call"""
        ...
