"""Authentication handler for Bakalari API."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import aiohttp

from ..const import (
    API_CLIENT_ID,
    API_LOGIN_ENDPOINT,
    GRANT_TYPE_PASSWORD,
    GRANT_TYPE_REFRESH,
    TOKEN_EXPIRY_BUFFER,
)

_LOGGER = logging.getLogger("bakalari.auth")


class BakalariAuthError(Exception):
    """Base exception for authentication errors."""


class BakalariInvalidCredentialsError(BakalariAuthError):
    """Invalid username or password."""


class BakalariTokenExpiredError(BakalariAuthError):
    """Token has expired and refresh failed."""


@dataclass
class TokenData:
    """Holds authentication token data."""

    access_token: str
    refresh_token: str
    expires_at: datetime
    user_id: str | None = None
    api_version: str | None = None

    @property
    def is_expired(self) -> bool:
        """Check if the access token is expired or about to expire."""
        return datetime.now() >= self.expires_at - timedelta(seconds=TOKEN_EXPIRY_BUFFER)

    @classmethod
    def from_response(cls, data: dict[str, Any]) -> TokenData:
        """Create TokenData from API response."""
        expires_in = data.get("expires_in", 3599)
        return cls(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expires_at=datetime.now() + timedelta(seconds=expires_in),
            user_id=data.get("bak:UserId"),
            api_version=data.get("bak:ApiVersion"),
        )


class BakalariAuth:
    """Handles authentication with the Bakalari API."""

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._session = session
        self._token_data: TokenData | None = None
        self._lock = asyncio.Lock()
        self._owns_session = False

    @property
    def is_authenticated(self) -> bool:
        return self._token_data is not None

    @property
    def token_data(self) -> TokenData | None:
        return self._token_data

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._owns_session = True
        return self._session

    async def _make_auth_request(self, data: dict[str, str]) -> dict[str, Any]:
        session = await self._ensure_session()
        url = f"{self._base_url}{API_LOGIN_ENDPOINT}"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        try:
            async with session.post(url, data=data, headers=headers) as response:
                response_data = await response.json()

                if response.status == 200:
                    return response_data

                error = response_data.get("error", "unknown_error")
                error_description = response_data.get(
                    "error_description", "Unknown error occurred"
                )
                _LOGGER.error("Authentication failed: %s - %s", error, error_description)

                if error == "invalid_grant":
                    raise BakalariInvalidCredentialsError(error_description)
                raise BakalariAuthError(f"{error}: {error_description}")

        except aiohttp.ClientError as err:
            _LOGGER.error("Network error during authentication: %s", err)
            raise BakalariAuthError(f"Network error: {err}") from err

    async def login(self) -> TokenData:
        async with self._lock:
            _LOGGER.debug("Attempting login for user: %s", self._username)
            data = {
                "client_id": API_CLIENT_ID,
                "grant_type": GRANT_TYPE_PASSWORD,
                "username": self._username,
                "password": self._password,
            }
            response = await self._make_auth_request(data)
            self._token_data = TokenData.from_response(response)
            _LOGGER.info(
                "Successfully logged in. API version: %s, User ID: %s",
                self._token_data.api_version,
                self._token_data.user_id,
            )
            return self._token_data

    async def refresh_token(self) -> TokenData:
        async with self._lock:
            if self._token_data is None:
                raise BakalariAuthError("No token data available. Please login first.")
            _LOGGER.debug("Refreshing access token")
            data = {
                "client_id": API_CLIENT_ID,
                "grant_type": GRANT_TYPE_REFRESH,
                "refresh_token": self._token_data.refresh_token,
            }
            try:
                response = await self._make_auth_request(data)
                self._token_data = TokenData.from_response(response)
                _LOGGER.debug("Successfully refreshed access token")
                return self._token_data
            except BakalariInvalidCredentialsError as err:
                self._token_data = None
                raise BakalariTokenExpiredError(
                    "Refresh token expired. Please login again."
                ) from err

    async def get_valid_token(self) -> str:
        if self._token_data is None:
            raise BakalariAuthError("Not authenticated. Please login first.")
        if self._token_data.is_expired:
            _LOGGER.debug("Access token expired, refreshing...")
            await self.refresh_token()
        return self._token_data.access_token

    async def close(self) -> None:
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()
            self._session = None
