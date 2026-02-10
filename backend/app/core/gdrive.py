"""Google Drive API client for fetching weekly reports."""

from __future__ import annotations

import io
import json
import logging
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import aiohttp

_LOGGER = logging.getLogger("bakalari.gdrive")

GDRIVE_FILES_ENDPOINT = "https://www.googleapis.com/drive/v3/files"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_DOCS_MIME = "application/vnd.google-apps.document"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MAX_DOCUMENT_SIZE = 100 * 1024


@dataclass
class FolderInfo:
    id: str
    name: str


@dataclass
class WeeklyReport:
    week_number: int
    content: str
    file_name: str
    fetched_at: datetime


class GoogleDriveError(Exception):
    """Base exception for Google Drive errors."""


class GoogleDriveAuthError(GoogleDriveError):
    """Authentication error."""


class GoogleDriveNotFoundError(GoogleDriveError):
    """Resource not found."""


def get_school_week_number(target_date: date, school_year_start: date) -> int:
    start_monday = school_year_start - timedelta(days=school_year_start.weekday())
    target_monday = target_date - timedelta(days=target_date.weekday())
    return (target_monday - start_monday).days // 7 + 1


def get_school_year_start(target_date: date | None = None) -> date:
    if target_date is None:
        target_date = date.today()
    year = target_date.year
    if target_date.month < 9:
        year -= 1
    return date(year, 9, 1)


class GoogleDriveClient:
    """Client for accessing Google Drive files using service account."""

    def __init__(
        self,
        service_account_path: str,
        reports_folder_id: str,
        session: aiohttp.ClientSession,
        school_year_start: date | None = None,
    ) -> None:
        self._service_account_path = service_account_path
        self._reports_folder_id = reports_folder_id
        self._session = session
        self._school_year_start = school_year_start or get_school_year_start()
        self._access_token: str | None = None
        self._token_expires: datetime | None = None
        self._report_cache: dict[int, WeeklyReport] = {}

    async def _load_service_account(self) -> dict[str, Any]:
        try:
            path = Path(self._service_account_path)
            if not path.exists():
                raise GoogleDriveAuthError(
                    f"Service account file not found: {self._service_account_path}"
                )
            content = path.read_text(encoding="utf-8")
            return json.loads(content)
        except json.JSONDecodeError as err:
            raise GoogleDriveAuthError(f"Invalid service account JSON: {err}") from err
        except OSError as err:
            raise GoogleDriveAuthError(f"Cannot read service account file: {err}") from err

    async def _create_jwt(self, credentials: dict[str, Any]) -> str:
        import base64

        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        header = {"alg": "RS256", "typ": "JWT"}
        now = int(datetime.now().timestamp())
        claims = {
            "iss": credentials["client_email"],
            "scope": "https://www.googleapis.com/auth/drive.readonly",
            "aud": GOOGLE_TOKEN_ENDPOINT,
            "iat": now,
            "exp": now + 3600,
        }

        def b64_encode(data: bytes) -> str:
            return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

        header_b64 = b64_encode(json.dumps(header).encode())
        claims_b64 = b64_encode(json.dumps(claims).encode())
        signing_input = f"{header_b64}.{claims_b64}"

        private_key_pem = credentials["private_key"].encode()
        private_key = serialization.load_pem_private_key(private_key_pem, password=None)
        signature = private_key.sign(
            signing_input.encode(), padding.PKCS1v15(), hashes.SHA256(),
        )
        return f"{signing_input}.{b64_encode(signature)}"

    async def _get_access_token(self) -> str:
        if self._access_token and self._token_expires:
            if datetime.now() < self._token_expires - timedelta(minutes=5):
                return self._access_token

        credentials = await self._load_service_account()
        jwt = await self._create_jwt(credentials)
        data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": jwt,
        }
        try:
            async with self._session.post(
                GOOGLE_TOKEN_ENDPOINT, data=data,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status != 200:
                    text = await response.text()
                    raise GoogleDriveAuthError(f"Token exchange failed ({response.status}): {text}")
                result = await response.json()
                self._access_token = result["access_token"]
                self._token_expires = datetime.now() + timedelta(
                    seconds=result.get("expires_in", 3600)
                )
                return self._access_token
        except aiohttp.ClientError as err:
            raise GoogleDriveAuthError(f"Network error during authentication: {err}") from err

    async def _api_request(
        self, method: str, url: str, params: dict[str, str] | None = None, **kwargs,
    ) -> aiohttp.ClientResponse:
        token = await self._get_access_token()
        headers = {"Authorization": f"Bearer {token}", **kwargs.pop("headers", {})}
        try:
            return await self._session.request(
                method, url, params=params, headers=headers,
                timeout=aiohttp.ClientTimeout(total=30), **kwargs,
            )
        except aiohttp.ClientError as err:
            raise GoogleDriveError(f"Network error: {err}") from err

    async def list_folders(self, parent_id: str | None = None) -> list[FolderInfo]:
        folder_id = parent_id or self._reports_folder_id
        query = f"'{folder_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        params = {"q": query, "fields": "files(id, name)", "pageSize": "100"}
        response = await self._api_request("GET", GDRIVE_FILES_ENDPOINT, params=params)
        if response.status == 404:
            raise GoogleDriveNotFoundError(f"Folder not found: {folder_id}")
        if response.status != 200:
            text = await response.text()
            raise GoogleDriveError(f"Failed to list folders ({response.status}): {text}")
        result = await response.json()
        return [FolderInfo(id=f["id"], name=f["name"]) for f in result.get("files", [])]

    async def find_week_folder(self, week_number: int) -> str | None:
        folders = await self.list_folders()
        for folder in folders:
            name = folder.name.strip()
            if name == str(week_number):
                return folder.id
            patterns = [
                rf"^{week_number}$",
                rf"(?:week|týden|tyden|w)\s*{week_number}$",
                rf"^{week_number}\s*(?:week|týden|tyden)$",
                rf"(?:week|týden|tyden|w)[_-]?{week_number}$",
            ]
            for pattern in patterns:
                if re.match(pattern, name, re.IGNORECASE):
                    return folder.id
        return None

    async def _get_file_content(self, file_id: str, mime_type: str) -> str:
        if mime_type == GOOGLE_DOCS_MIME:
            url = f"{GDRIVE_FILES_ENDPOINT}/{file_id}/export"
            params = {"mimeType": "text/plain"}
        else:
            url = f"{GDRIVE_FILES_ENDPOINT}/{file_id}"
            params = {"alt": "media"}

        response = await self._api_request("GET", url, params=params)
        if response.status == 404:
            raise GoogleDriveNotFoundError(f"File not found: {file_id}")
        if response.status != 200:
            text = await response.text()
            raise GoogleDriveError(f"Failed to get file ({response.status}): {text}")

        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > MAX_DOCUMENT_SIZE:
            raise GoogleDriveError(f"Document too large: {content_length} bytes")

        if mime_type == DOCX_MIME:
            return await self._extract_docx_text(await response.read())
        return await response.text()

    async def _extract_docx_text(self, content: bytes) -> str:
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                with zf.open("word/document.xml") as doc_file:
                    tree = ET.parse(doc_file)
                    root = tree.getroot()
                    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                    texts: list[str] = []
                    for elem in root.iter():
                        if elem.tag == f"{{{ns['w']}}}t" or elem.tag.endswith("}t"):
                            if elem.text:
                                texts.append(elem.text)
                        elif elem.tag == f"{{{ns['w']}}}p" or elem.tag.endswith("}p"):
                            texts.append("\n")
                    return "".join(texts).strip()
        except (zipfile.BadZipFile, KeyError, ET.ParseError) as err:
            raise GoogleDriveError(f"Failed to parse DOCX: {err}") from err

    def _matches_week_number(self, filename: str, week_number: int) -> bool:
        """Check if a filename matches a week number pattern.

        Matches 'Week 14.docx', 'Week 16 (15.12-19.12).docx', etc.
        Uses word boundary after the number to avoid partial matches.
        """
        name = filename.strip()
        patterns = [
            rf"^(?:week|týden|tyden|w)[\s_-]*{week_number}\b",
            rf"^{week_number}\s+(?:week|týden|tyden)\b",
        ]
        return any(re.match(p, name, re.IGNORECASE) for p in patterns)

    async def _find_week_file_in_subfolders(self, week_number: int) -> dict[str, str] | None:
        """Search month subfolders for a file matching 'Week N'."""
        subfolders = await self.list_folders()
        for folder in subfolders:
            query = f"'{folder.id}' in parents and trashed = false"
            params = {"q": query, "fields": "files(id, name, mimeType)", "pageSize": "50"}
            response = await self._api_request("GET", GDRIVE_FILES_ENDPOINT, params=params)
            if response.status != 200:
                continue
            files = (await response.json()).get("files", [])
            for file in files:
                if self._matches_week_number(file.get("name", ""), week_number):
                    mime = file.get("mimeType", "")
                    if mime in (GOOGLE_DOCS_MIME, DOCX_MIME, "text/plain"):
                        return file
        return None

    async def get_week_report(
        self, week_number: int | None = None, target_date: date | None = None,
    ) -> WeeklyReport | None:
        if week_number is None:
            if target_date is None:
                target_date = date.today()
            week_number = get_school_week_number(target_date, self._school_year_start)

        if week_number in self._report_cache:
            cached = self._report_cache[week_number]
            if datetime.now() - cached.fetched_at < timedelta(hours=1):
                return cached

        # Search month subfolders for "Week N" files
        document = await self._find_week_file_in_subfolders(week_number)

        # Fallback: look for a dedicated week folder (e.g. folder named "14")
        if not document:
            folder_id = await self.find_week_folder(week_number)
            if folder_id:
                query = f"'{folder_id}' in parents and trashed = false"
                params = {"q": query, "fields": "files(id, name, mimeType)", "pageSize": "20"}
                response = await self._api_request("GET", GDRIVE_FILES_ENDPOINT, params=params)
                if response.status == 200:
                    files = (await response.json()).get("files", [])
                    for file in files:
                        mime = file.get("mimeType", "")
                        if mime in (GOOGLE_DOCS_MIME, DOCX_MIME, "text/plain"):
                            document = file
                            break

        if not document:
            _LOGGER.info("No report found for school week %d", week_number)
            return None

        content = await self._get_file_content(document["id"], document["mimeType"])
        report = WeeklyReport(
            week_number=week_number, content=content,
            file_name=document["name"], fetched_at=datetime.now(),
        )
        self._report_cache[week_number] = report
        _LOGGER.info("Fetched weekly report for week %d: %s", week_number, document["name"])
        return report

    def clear_cache(self) -> None:
        self._report_cache.clear()

    async def test_connection(self) -> bool:
        try:
            await self._get_access_token()
            await self.list_folders()
            return True
        except GoogleDriveError as err:
            _LOGGER.error("Google Drive connection test failed: %s", err)
            return False
