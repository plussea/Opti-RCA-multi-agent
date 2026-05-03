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
        """Parse JSON from model response — handles all malformed cases.

        Tries 5 strategies in order:
        1. Direct parse (works if content is clean JSON)
        2. Strip markdown fences then parse
        3. Isolate first { ... } block and parse
        4. json.JSONDecoder.raw_decode() — handles trailing garbage after first object
        5. Extract first { ... } from anywhere, collapse bare newlines inside strings
        """
        content = self._normalize_llm_response(content)
        raw = content.strip()

        # Strategy 1
        try:
            return dict(json.loads(raw))
        except json.JSONDecodeError:
            pass

        # Strategy 2: strip markdown fences
        stripped = raw
        for _fence in ("```json", "```"):
            stripped = stripped.lstrip()
            if stripped.startswith(_fence):
                stripped = stripped[len(_fence):].lstrip()
            stripped = re.sub(r"```\s*$", "", stripped, flags=re.MULTILINE).strip()
        try:
            return dict(json.loads(stripped))
        except json.JSONDecodeError:
            pass

        # Strategy 3: isolate first { ... } block
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = raw[start:end + 1]
            try:
                return dict(json.loads(candidate))
            except json.JSONDecodeError:
                pass

        # Strategy 4: raw_decode handles trailing garbage after first complete object
        decoder = json.JSONDecoder()
        try:
            obj, _ = decoder.raw_decode(raw)
            return dict(obj)
        except json.JSONDecodeError:
            pass

        # Strategy 5: extract first { ... } from anywhere, collapse bare newlines
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            candidate = match.group(0)
            compact = re.sub(r"(?<!\\)\n", " ", candidate)
            compact = re.sub(r"(?<!\\)\r", "", compact)
            try:
                return dict(json.loads(compact))
            except json.JSONDecodeError:
                pass

        raise ValueError(f"Failed to parse JSON (tried 5 strategies): {content[:500]}") from None

    def _normalize_llm_response(self, content: str) -> str:
        """Normalize LLM response: strip BOM, control chars, normalize line endings."""
        import logging
        logger = logging.getLogger(__name__)
        original = content
        # Remove BOM
        if content.startswith("﻿"):
            content = content[1:]
        # Normalize line endings
        content = content.replace("\r\n", "\n").replace("\r", "\n")
        # Strip zero-width and control chars (keep tab/newline)
        content = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", content)
        # Strip leading non-JSON text before first {
        first_brace = content.find("{")
        if first_brace > 0:
            content = content[first_brace:]
        if content != original and logger.isEnabledFor(10):
            logger.debug(f"[JSON parser] normalized: {content[:200]}")
        return content

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