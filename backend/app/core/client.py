"""Base API client for Bakalari."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .auth import (
    BakalariAuth,
    BakalariAuthError,
    BakalariTokenExpiredError,
)

_LOGGER = logging.getLogger("bakalari.client")


class BakalariApiError(Exception):
    """Base exception for API errors."""


class BakalariClient:
    """Client for making authenticated requests to the Bakalari API."""

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._session = session
        self._owns_session = False
        self._auth = BakalariAuth(base_url, username, password, session)

    @property
    def auth(self) -> BakalariAuth:
        return self._auth

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._owns_session = True
        return self._session

    async def login(self) -> bool:
        await self._auth.login()
        return True

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        retry_on_auth_error: bool = True,
    ) -> dict[str, Any]:
        session = await self._ensure_session()
        url = f"{self._base_url}{endpoint}"

        try:
            token = await self._auth.get_valid_token()
        except BakalariTokenExpiredError:
            _LOGGER.info("Token expired, attempting re-login")
            await self._auth.login()
            token = await self._auth.get_valid_token()

        headers: dict[str, str] = {"Authorization": f"Bearer {token}"}
        request_kwargs: dict[str, Any] = {"params": params, "headers": headers}

        if json_data is not None:
            request_kwargs["json"] = json_data
        elif data is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            request_kwargs["data"] = data

        _LOGGER.debug("API request: %s %s", method, endpoint)

        try:
            async with session.request(method, url, **request_kwargs) as response:
                if response.status == 401 and retry_on_auth_error:
                    _LOGGER.debug("Got 401, attempting token refresh and retry")
                    try:
                        await self._auth.refresh_token()
                        return await self._request(
                            method, endpoint, params, data, json_data,
                            retry_on_auth_error=False,
                        )
                    except BakalariTokenExpiredError:
                        await self._auth.login()
                        return await self._request(
                            method, endpoint, params, data, json_data,
                            retry_on_auth_error=False,
                        )

                if response.status == 401:
                    raise BakalariAuthError("Authentication failed")
                if response.status == 405:
                    raise BakalariApiError(
                        f"Method {method} not allowed for endpoint {endpoint}"
                    )
                if response.status not in (200, 204):
                    text = await response.text()
                    _LOGGER.error(
                        "API error: %s %s returned status %s: %s",
                        method, endpoint, response.status, text[:500],
                    )
                    raise BakalariApiError(
                        f"API request failed with status {response.status}: {text}"
                    )
                if response.status == 204:
                    return {}
                return await response.json()

        except aiohttp.ClientError as err:
            _LOGGER.error("Network error during API request: %s", err)
            raise BakalariApiError(f"Network error: {err}") from err

    async def get(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return await self._request("GET", endpoint, params=params)

    async def post(
        self,
        endpoint: str,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "POST", endpoint, params=params, data=data, json_data=json_data
        )

    async def put(
        self, endpoint: str, data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return await self._request("PUT", endpoint, data=data)

    async def close(self) -> None:
        await self._auth.close()
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()
            self._session = None
