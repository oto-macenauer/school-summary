"""Shared fixtures for Bakalari backend tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from aiohttp import ClientResponse, ClientSession

# Path to fixtures directory
FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(filename: str) -> dict[str, Any]:
    """Load a JSON fixture file."""
    with open(FIXTURES_DIR / filename, encoding="utf-8") as f:
        return json.load(f)


# Test configuration
TEST_BASE_URL = "https://bakalari.test.school.cz"
TEST_USERNAME = "test_user"
TEST_PASSWORD = "test_password"


@pytest.fixture
def base_url() -> str:
    """Return test base URL."""
    return TEST_BASE_URL


@pytest.fixture
def test_credentials() -> dict[str, str]:
    """Return test credentials."""
    return {
        "username": TEST_USERNAME,
        "password": TEST_PASSWORD,
    }


@pytest.fixture
def login_response() -> dict[str, Any]:
    """Return a successful login response."""
    return load_fixture("login_response.json")


@pytest.fixture
def login_error_invalid_credentials() -> dict[str, Any]:
    """Return an invalid credentials error response."""
    return load_fixture("login_error_invalid_credentials.json")


@pytest.fixture
def login_error_invalid_refresh() -> dict[str, Any]:
    """Return an invalid refresh token error response."""
    return load_fixture("login_error_invalid_refresh.json")


def create_mock_response(
    status: int, json_data: dict[str, Any] | None = None, text: str = ""
) -> AsyncMock:
    """Create a mock aiohttp response."""
    mock_response = AsyncMock(spec=ClientResponse)
    mock_response.status = status
    mock_response.json = AsyncMock(return_value=json_data or {})
    mock_response.text = AsyncMock(return_value=text)

    # Support async context manager
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    return mock_response


@pytest.fixture
def mock_session() -> MagicMock:
    """Create a mock aiohttp session."""
    session = MagicMock(spec=ClientSession)
    session.closed = False
    session.close = AsyncMock()
    return session


@pytest.fixture
def real_credentials() -> dict[str, str] | None:
    """Load real credentials from environment for integration tests.

    Returns None if credentials are not available.
    """
    from dotenv import load_dotenv

    load_dotenv()

    base_url = os.getenv("BAKALARI_URL")
    username = os.getenv("BAKALARI_USERNAME")
    password = os.getenv("BAKALARI_PASSWORD")

    if not all([base_url, username, password]):
        return None

    return {
        "base_url": base_url,
        "username": username,
        "password": password,
    }


# Pytest markers
def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests (require real API)"
    )
