"""Tests for the authentication module."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.auth import (
    BakalariAuth,
    BakalariAuthError,
    BakalariInvalidCredentialsError,
    BakalariTokenExpiredError,
    TokenData,
)
from app.const import TOKEN_EXPIRY_BUFFER

from .conftest import TEST_BASE_URL, TEST_PASSWORD, TEST_USERNAME, create_mock_response


class TestTokenData:
    """Tests for TokenData dataclass."""

    def test_from_response(self, login_response: dict[str, Any]) -> None:
        """Test creating TokenData from API response."""
        token_data = TokenData.from_response(login_response)

        assert token_data.access_token == login_response["access_token"]
        assert token_data.refresh_token == login_response["refresh_token"]
        assert token_data.user_id == login_response["bak:UserId"]
        assert token_data.api_version == login_response["bak:ApiVersion"]
        assert token_data.expires_at > datetime.now()

    def test_is_expired_false_when_fresh(self, login_response: dict[str, Any]) -> None:
        """Test that fresh token is not expired."""
        token_data = TokenData.from_response(login_response)
        assert token_data.is_expired is False

    def test_is_expired_true_when_about_to_expire(self) -> None:
        """Test that token is considered expired when within buffer."""
        token_data = TokenData(
            access_token="test",
            refresh_token="test",
            expires_at=datetime.now() + timedelta(seconds=TOKEN_EXPIRY_BUFFER - 10),
        )
        assert token_data.is_expired is True

    def test_is_expired_true_when_past(self) -> None:
        """Test that past token is expired."""
        token_data = TokenData(
            access_token="test",
            refresh_token="test",
            expires_at=datetime.now() - timedelta(seconds=100),
        )
        assert token_data.is_expired is True


class TestBakalariAuth:
    """Tests for BakalariAuth class."""

    @pytest.fixture
    def auth(self) -> BakalariAuth:
        """Create a BakalariAuth instance for testing."""
        return BakalariAuth(TEST_BASE_URL, TEST_USERNAME, TEST_PASSWORD)

    @pytest.mark.asyncio
    async def test_login_success(
        self, auth: BakalariAuth, login_response: dict[str, Any]
    ) -> None:
        """Test successful login."""
        mock_response = create_mock_response(200, login_response)

        with patch.object(auth, "_ensure_session") as mock_ensure:
            mock_session = MagicMock()
            mock_session.post = MagicMock(return_value=mock_response)
            mock_ensure.return_value = mock_session

            token_data = await auth.login()

            assert auth.is_authenticated is True
            assert token_data.access_token == login_response["access_token"]
            assert token_data.user_id == login_response["bak:UserId"]

    @pytest.mark.asyncio
    async def test_login_invalid_credentials(
        self, auth: BakalariAuth, login_error_invalid_credentials: dict[str, Any]
    ) -> None:
        """Test login with invalid credentials."""
        mock_response = create_mock_response(400, login_error_invalid_credentials)

        with patch.object(auth, "_ensure_session") as mock_ensure:
            mock_session = MagicMock()
            mock_session.post = MagicMock(return_value=mock_response)
            mock_ensure.return_value = mock_session

            with pytest.raises(BakalariInvalidCredentialsError):
                await auth.login()

    @pytest.mark.asyncio
    async def test_refresh_token_success(
        self, auth: BakalariAuth, login_response: dict[str, Any]
    ) -> None:
        """Test successful token refresh."""
        # First, set up initial token data
        auth._token_data = TokenData.from_response(login_response)
        old_access_token = auth._token_data.access_token

        # Prepare new response with different token
        new_response = login_response.copy()
        new_response["access_token"] = "new_access_token_12345"
        mock_response = create_mock_response(200, new_response)

        with patch.object(auth, "_ensure_session") as mock_ensure:
            mock_session = MagicMock()
            mock_session.post = MagicMock(return_value=mock_response)
            mock_ensure.return_value = mock_session

            new_token_data = await auth.refresh_token()

            assert new_token_data.access_token == "new_access_token_12345"
            assert new_token_data.access_token != old_access_token

    @pytest.mark.asyncio
    async def test_refresh_token_without_login(self, auth: BakalariAuth) -> None:
        """Test refresh token fails when not logged in."""
        with pytest.raises(BakalariAuthError, match="No token data available"):
            await auth.refresh_token()

    @pytest.mark.asyncio
    async def test_refresh_token_expired(
        self,
        auth: BakalariAuth,
        login_response: dict[str, Any],
        login_error_invalid_refresh: dict[str, Any],
    ) -> None:
        """Test handling of expired refresh token."""
        auth._token_data = TokenData.from_response(login_response)

        mock_response = create_mock_response(400, login_error_invalid_refresh)

        with patch.object(auth, "_ensure_session") as mock_ensure:
            mock_session = MagicMock()
            mock_session.post = MagicMock(return_value=mock_response)
            mock_ensure.return_value = mock_session

            with pytest.raises(BakalariTokenExpiredError):
                await auth.refresh_token()

            # Token data should be cleared
            assert auth._token_data is None

    @pytest.mark.asyncio
    async def test_get_valid_token_when_valid(
        self, auth: BakalariAuth, login_response: dict[str, Any]
    ) -> None:
        """Test getting valid token when it's still valid."""
        auth._token_data = TokenData.from_response(login_response)

        token = await auth.get_valid_token()

        assert token == login_response["access_token"]

    @pytest.mark.asyncio
    async def test_get_valid_token_refreshes_when_expired(
        self, auth: BakalariAuth, login_response: dict[str, Any]
    ) -> None:
        """Test that get_valid_token refreshes an expired token."""
        # Set up expired token
        auth._token_data = TokenData(
            access_token="old_token",
            refresh_token=login_response["refresh_token"],
            expires_at=datetime.now() - timedelta(seconds=100),
            user_id="test",
        )

        new_response = login_response.copy()
        new_response["access_token"] = "new_refreshed_token"
        mock_response = create_mock_response(200, new_response)

        with patch.object(auth, "_ensure_session") as mock_ensure:
            mock_session = MagicMock()
            mock_session.post = MagicMock(return_value=mock_response)
            mock_ensure.return_value = mock_session

            token = await auth.get_valid_token()

            assert token == "new_refreshed_token"

    @pytest.mark.asyncio
    async def test_get_valid_token_not_authenticated(self, auth: BakalariAuth) -> None:
        """Test get_valid_token raises when not authenticated."""
        with pytest.raises(BakalariAuthError, match="Not authenticated"):
            await auth.get_valid_token()

    @pytest.mark.asyncio
    async def test_close_session(self, auth: BakalariAuth) -> None:
        """Test closing the session."""
        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.close = AsyncMock()

        auth._session = mock_session
        auth._owns_session = True

        await auth.close()

        mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_does_not_close_external_session(
        self, auth: BakalariAuth
    ) -> None:
        """Test that external session is not closed."""
        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.close = AsyncMock()

        auth._session = mock_session
        auth._owns_session = False

        await auth.close()

        mock_session.close.assert_not_called()

    def test_is_authenticated_false_initially(self, auth: BakalariAuth) -> None:
        """Test that auth is not authenticated initially."""
        assert auth.is_authenticated is False

    def test_base_url_trailing_slash_removed(self) -> None:
        """Test that trailing slash is removed from base URL."""
        auth = BakalariAuth("https://example.com/", "user", "pass")
        assert auth._base_url == "https://example.com"


class TestBakalariAuthIntegration:
    """Integration tests for BakalariAuth (require real API)."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_real_login(self, real_credentials: dict[str, str] | None) -> None:
        """Test login with real credentials."""
        if real_credentials is None:
            pytest.skip("Real credentials not available")

        auth = BakalariAuth(
            real_credentials["base_url"],
            real_credentials["username"],
            real_credentials["password"],
        )

        try:
            token_data = await auth.login()

            assert token_data.access_token is not None
            assert token_data.refresh_token is not None
            assert token_data.user_id is not None
            assert auth.is_authenticated is True
        finally:
            await auth.close()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_real_token_refresh(
        self, real_credentials: dict[str, str] | None
    ) -> None:
        """Test token refresh with real API."""
        if real_credentials is None:
            pytest.skip("Real credentials not available")

        auth = BakalariAuth(
            real_credentials["base_url"],
            real_credentials["username"],
            real_credentials["password"],
        )

        try:
            await auth.login()
            old_token = auth.token_data.access_token

            new_token_data = await auth.refresh_token()

            assert new_token_data.access_token is not None
            # New token should be different (usually)
            assert new_token_data.refresh_token is not None
        finally:
            await auth.close()
