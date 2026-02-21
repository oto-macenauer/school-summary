"""Tests for Gemini API client."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.gemini import (
    GeminiClient,
    GeminiApiError,
    GeminiRateLimitError,
    GeminiInvalidKeyError,
    GeminiUsageStats,
    DAILY_REQUEST_LIMIT,
    DAILY_TOKEN_LIMIT,
)


@pytest.fixture
def mock_session():
    """Create a mock aiohttp session."""
    session = MagicMock()
    session.closed = False
    session.close = AsyncMock()
    return session


@pytest.fixture
def gemini_client(mock_session):
    """Create a Gemini client instance."""
    return GeminiClient(
        api_key="test_api_key",
        session=mock_session,
        model="gemini-2.5-flash-lite",
    )


@pytest.fixture
def successful_response():
    """Return a successful Gemini API response."""
    return {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "Tento týden Alice dostala novou známku z matematiky."}
                    ]
                }
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 150,
            "candidatesTokenCount": 50,
            "totalTokenCount": 200,
        }
    }


@pytest.fixture
def error_response():
    """Return an error response."""
    return {
        "error": {
            "code": 400,
            "message": "Invalid request",
            "status": "INVALID_ARGUMENT"
        }
    }


def create_mock_response(status: int, json_data: dict) -> AsyncMock:
    """Create a mock aiohttp response."""
    mock = AsyncMock()
    mock.status = status
    mock.json = AsyncMock(return_value=json_data)
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=None)
    return mock


@pytest.mark.asyncio
async def test_generate_content_success(gemini_client, mock_session, successful_response):
    """Test successful content generation."""
    mock_response = create_mock_response(200, successful_response)
    mock_session.post = MagicMock(return_value=mock_response)

    result = await gemini_client.generate_content(
        prompt="Shrň školní aktivity",
        system_instruction="Jsi asistent pro rodiče.",
    )

    assert result == "Tento týden Alice dostala novou známku z matematiky."
    mock_session.post.assert_called_once()


@pytest.mark.asyncio
async def test_generate_content_rate_limit(gemini_client, mock_session):
    """Test rate limit error handling."""
    error_response = {
        "error": {"message": "Rate limit exceeded"}
    }
    mock_response = create_mock_response(429, error_response)
    mock_session.post = MagicMock(return_value=mock_response)

    with pytest.raises(GeminiRateLimitError):
        await gemini_client.generate_content(prompt="Test")


@pytest.mark.asyncio
async def test_generate_content_invalid_key(gemini_client, mock_session):
    """Test invalid API key error handling."""
    error_response = {
        "error": {"message": "Invalid API key"}
    }
    mock_response = create_mock_response(401, error_response)
    mock_session.post = MagicMock(return_value=mock_response)

    with pytest.raises(GeminiInvalidKeyError):
        await gemini_client.generate_content(prompt="Test")


@pytest.mark.asyncio
async def test_generate_content_forbidden(gemini_client, mock_session):
    """Test forbidden error handling."""
    error_response = {
        "error": {"message": "Permission denied"}
    }
    mock_response = create_mock_response(403, error_response)
    mock_session.post = MagicMock(return_value=mock_response)

    with pytest.raises(GeminiInvalidKeyError):
        await gemini_client.generate_content(prompt="Test")


@pytest.mark.asyncio
async def test_generate_content_api_error(gemini_client, mock_session, error_response):
    """Test general API error handling."""
    mock_response = create_mock_response(400, error_response)
    mock_session.post = MagicMock(return_value=mock_response)

    with pytest.raises(GeminiApiError):
        await gemini_client.generate_content(prompt="Test")


@pytest.mark.asyncio
async def test_generate_content_empty_candidates(gemini_client, mock_session):
    """Test handling of empty candidates."""
    empty_response = {"candidates": []}
    mock_response = create_mock_response(200, empty_response)
    mock_session.post = MagicMock(return_value=mock_response)

    with pytest.raises(GeminiApiError, match="No candidates"):
        await gemini_client.generate_content(prompt="Test")


@pytest.mark.asyncio
async def test_generate_content_empty_parts(gemini_client, mock_session):
    """Test handling of empty parts."""
    empty_parts_response = {
        "candidates": [{"content": {"parts": []}}]
    }
    mock_response = create_mock_response(200, empty_parts_response)
    mock_session.post = MagicMock(return_value=mock_response)

    with pytest.raises(GeminiApiError, match="No parts"):
        await gemini_client.generate_content(prompt="Test")


@pytest.mark.asyncio
async def test_close_session(gemini_client, mock_session):
    """Test session is not closed when not owned."""
    await gemini_client.close()
    # Session wasn't created by client, so it shouldn't be closed
    mock_session.close.assert_not_called()


@pytest.mark.asyncio
async def test_close_owned_session():
    """Test session is closed when owned."""
    client = GeminiClient(api_key="test_key", model="gemini-2.5-flash-lite")
    mock_session = MagicMock()
    mock_session.closed = False
    mock_session.close = AsyncMock()
    client._session = mock_session
    client._owns_session = True

    await client.close()
    mock_session.close.assert_called_once()


@pytest.mark.asyncio
async def test_usage_tracking(gemini_client, mock_session, successful_response):
    """Test that usage stats are tracked after successful request."""
    mock_response = create_mock_response(200, successful_response)
    mock_session.post = MagicMock(return_value=mock_response)

    # Initial state
    assert gemini_client.usage_stats.requests_today == 0
    assert gemini_client.usage_stats.tokens_today == 0

    await gemini_client.generate_content(prompt="Test")

    # After request
    assert gemini_client.usage_stats.requests_today == 1
    assert gemini_client.usage_stats.tokens_today == 200  # 150 + 50
    assert gemini_client.usage_stats.last_prompt_tokens == 150
    assert gemini_client.usage_stats.last_response_tokens == 50


class TestGeminiUsageStats:
    """Tests for GeminiUsageStats."""

    def test_initial_state(self):
        """Test initial state of usage stats."""
        stats = GeminiUsageStats()
        assert stats.requests_today == 0
        assert stats.tokens_today == 0
        assert stats.requests_remaining == DAILY_REQUEST_LIMIT
        assert stats.tokens_remaining == DAILY_TOKEN_LIMIT

    def test_record_request(self):
        """Test recording a request."""
        stats = GeminiUsageStats()
        stats.record_request(100, 50)

        assert stats.requests_today == 1
        assert stats.tokens_today == 150
        assert stats.last_prompt_tokens == 100
        assert stats.last_response_tokens == 50
        assert stats.last_request_time is not None

    def test_multiple_requests(self):
        """Test multiple requests accumulate."""
        stats = GeminiUsageStats()
        stats.record_request(100, 50)
        stats.record_request(200, 100)

        assert stats.requests_today == 2
        assert stats.tokens_today == 450  # 150 + 300

    def test_remaining_calculations(self):
        """Test remaining tokens and requests calculation."""
        stats = GeminiUsageStats()
        stats.record_request(100, 50)

        assert stats.requests_remaining == DAILY_REQUEST_LIMIT - 1
        assert stats.tokens_remaining == DAILY_TOKEN_LIMIT - 150

    def test_to_dict(self):
        """Test conversion to dictionary."""
        stats = GeminiUsageStats()
        stats.record_request(100, 50)

        result = stats.to_dict()

        assert result["requests_today"] == 1
        assert result["tokens_today"] == 150
        assert result["requests_remaining"] == DAILY_REQUEST_LIMIT - 1
        assert result["tokens_remaining"] == DAILY_TOKEN_LIMIT - 150
        assert result["requests_limit"] == DAILY_REQUEST_LIMIT
        assert result["tokens_limit"] == DAILY_TOKEN_LIMIT
        assert result["last_prompt_tokens"] == 100
        assert result["last_response_tokens"] == 50
        assert result["last_request"] is not None
