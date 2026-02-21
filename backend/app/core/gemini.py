"""Gemini API client for generating summaries."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import aiohttp

from ..const import GEMINI_API_URL

_LOGGER = logging.getLogger("bakalari.gemini")

DAILY_REQUEST_LIMIT = 1500
DAILY_TOKEN_LIMIT = 1_000_000


@dataclass
class GeminiUsageStats:
    """Track Gemini API usage statistics."""

    requests_today: int = 0
    tokens_today: int = 0
    last_reset_date: date = field(default_factory=date.today)
    last_request_time: datetime | None = None
    last_prompt_tokens: int = 0
    last_response_tokens: int = 0

    def reset_if_new_day(self) -> None:
        today = date.today()
        if today > self.last_reset_date:
            self.requests_today = 0
            self.tokens_today = 0
            self.last_reset_date = today

    def record_request(self, prompt_tokens: int, response_tokens: int) -> None:
        self.reset_if_new_day()
        self.requests_today += 1
        self.tokens_today += prompt_tokens + response_tokens
        self.last_request_time = datetime.now()
        self.last_prompt_tokens = prompt_tokens
        self.last_response_tokens = response_tokens

    @property
    def requests_remaining(self) -> int:
        self.reset_if_new_day()
        return max(0, DAILY_REQUEST_LIMIT - self.requests_today)

    @property
    def tokens_remaining(self) -> int:
        self.reset_if_new_day()
        return max(0, DAILY_TOKEN_LIMIT - self.tokens_today)

    def to_dict(self) -> dict[str, Any]:
        self.reset_if_new_day()
        return {
            "requests_today": self.requests_today,
            "requests_remaining": self.requests_remaining,
            "requests_limit": DAILY_REQUEST_LIMIT,
            "tokens_today": self.tokens_today,
            "tokens_remaining": self.tokens_remaining,
            "tokens_limit": DAILY_TOKEN_LIMIT,
            "last_request": self.last_request_time.isoformat() if self.last_request_time else None,
            "last_prompt_tokens": self.last_prompt_tokens,
            "last_response_tokens": self.last_response_tokens,
        }


class GeminiApiError(Exception):
    """Base exception for Gemini API errors."""


class GeminiRateLimitError(GeminiApiError):
    """Rate limit exceeded."""


class GeminiInvalidKeyError(GeminiApiError):
    """Invalid API key."""


class GeminiClient:
    """Async client for Google Gemini API."""

    def __init__(
        self,
        api_key: str,
        session: aiohttp.ClientSession | None = None,
        *,
        model: str,
    ) -> None:
        self._api_key = api_key
        self._session = session
        self._model = model
        self._owns_session = False
        self.usage_stats = GeminiUsageStats()

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._owns_session = True
        return self._session

    async def generate_content(
        self,
        prompt: str,
        system_instruction: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        session = await self._ensure_session()
        url = f"{GEMINI_API_URL}/{self._model}:generateContent"

        payload: dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature,
            },
        }
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        params = {"key": self._api_key}
        _LOGGER.debug("Gemini API request: model=%s, prompt_length=%d", self._model, len(prompt))

        try:
            async with session.post(
                url, json=payload, params=params,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as response:
                response_data = await response.json()

                if response.status == 200:
                    usage = response_data.get("usageMetadata", {})
                    prompt_tokens = usage.get("promptTokenCount", 0)
                    response_tokens = usage.get("candidatesTokenCount", 0)
                    self.usage_stats.record_request(prompt_tokens, response_tokens)
                    return self._extract_text(response_data)

                error_message = self._extract_error(response_data)

                if response.status == 429:
                    raise GeminiRateLimitError(f"Rate limit exceeded: {error_message}")
                if response.status in (401, 403):
                    raise GeminiInvalidKeyError(
                        f"Invalid API key or access forbidden: {error_message}"
                    )
                raise GeminiApiError(
                    f"API request failed ({response.status}): {error_message}"
                )

        except aiohttp.ClientError as err:
            _LOGGER.error("Network error during Gemini API request: %s", err)
            raise GeminiApiError(f"Network error: {err}") from err

    def _extract_text(self, response: dict[str, Any]) -> str:
        try:
            candidates = response.get("candidates", [])
            if not candidates:
                raise GeminiApiError("No candidates in response")
            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                raise GeminiApiError("No parts in response content")
            return parts[0].get("text", "")
        except (KeyError, IndexError) as err:
            raise GeminiApiError(f"Invalid response format: {err}") from err

    def _extract_error(self, response: dict[str, Any]) -> str:
        return response.get("error", {}).get("message", "Unknown error")

    async def close(self) -> None:
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()
            self._session = None
