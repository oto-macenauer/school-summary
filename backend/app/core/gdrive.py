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

SCHOOL_YEAR_ANCHOR_MONTH = 9
SCHOOL_YEAR_ANCHOR_DAY = 1
MAX_SCHOOL_WEEK = 53

# Report file names are inconsistent: 'Week 3.docx', 'Weekly report 2.docx',
# 'Týden 16 (15.12-19.12).docx', '14 Week.docx'.  Match a week keyword next to
# a one- or two-digit number anywhere in the name, in either order.
_WEEK_KEYWORD_PATTERN = re.compile(
    r"(?:weekly|week|wk|w|týden|tyden|report)[\s._-]*(\d{1,2})(?!\d)",
    re.IGNORECASE,
)
_WEEK_SUFFIX_PATTERN = re.compile(
    r"(?<!\d)(\d{1,2})[\s._-]*(?:weekly|week|wk|týden|tyden|report)",
    re.IGNORECASE,
)
_STANDALONE_NUMBER_PATTERN = re.compile(r"(?<!\d)(\d{1,2})(?!\d)")


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
    school_year: str = ""


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


def get_school_year_start(
    target_date: date | None = None, anchor: date | None = None,
) -> date:
    """Start date of the school year that contains ``target_date``.

    Only the month and day of ``anchor`` are used, so a configured anchor such
    as ``2025-09-01`` keeps marking the September rollover in every later year
    instead of freezing the school year it was written in.
    """
    if target_date is None:
        target_date = date.today()
    month = anchor.month if anchor else SCHOOL_YEAR_ANCHOR_MONTH
    day = anchor.day if anchor else SCHOOL_YEAR_ANCHOR_DAY
    year = target_date.year
    if (target_date.month, target_date.day) < (month, day):
        year -= 1
    return date(year, month, day)


def school_year_label(start: date) -> str:
    """Human label of the school year starting at ``start``, e.g. ``2026/2027``."""
    return f"{start.year}/{start.year + 1}"


def school_year_slug(school_year: str) -> str:
    """Filesystem-safe school year: ``2026/2027`` -> ``2026-2027``."""
    return school_year.strip().replace("/", "-")


def current_school_year(anchor: date | None = None) -> str:
    """Label of the school year in progress today."""
    return school_year_label(get_school_year_start(anchor=anchor))


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
        # Only the month/day matter: the anchor marks the rollover, the year is
        # derived from whatever date we are resolving.
        self._school_year_anchor = school_year_start
        self._access_token: str | None = None
        self._token_expires: datetime | None = None
        self._report_cache: dict[tuple[str, int], WeeklyReport] = {}

    @property
    def school_year_start(self) -> date:
        """Start of the school year in progress today."""
        return get_school_year_start(anchor=self._school_year_anchor)

    @property
    def school_year(self) -> str:
        """Label of the school year in progress today, e.g. ``2026/2027``."""
        return school_year_label(self.school_year_start)

    def school_year_start_for(self, target_date: date) -> date:
        """Start of the school year containing ``target_date``."""
        return get_school_year_start(target_date, self._school_year_anchor)

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
        """Check whether a filename names a given week."""
        return self.week_number_from_name(filename) == week_number

    def week_number_from_name(self, filename: str, strict: bool = True) -> int | None:
        """Week number a report file name refers to, or None if it is unclear.

        The keyword may sit anywhere in the name, so 'Week 3.docx',
        'Weekly report 2.docx' and '14 Week.docx' all resolve.  With
        ``strict=False`` a name carrying exactly one unambiguous number counts
        even without a keyword — month subfolders hold nothing but reports, so
        there is no other kind of file for a stray number to belong to.
        """
        stem = Path(filename.strip()).stem

        for pattern in (_WEEK_KEYWORD_PATTERN, _WEEK_SUFFIX_PATTERN):
            match = pattern.search(stem)
            if match:
                return self._valid_week(int(match.group(1)))

        if strict:
            return None

        numbers = {int(n) for n in _STANDALONE_NUMBER_PATTERN.findall(stem)}
        if len(numbers) != 1:
            return None
        return self._valid_week(numbers.pop())

    @staticmethod
    def _valid_week(week_number: int) -> int | None:
        return week_number if 1 <= week_number <= MAX_SCHOOL_WEEK else None

    async def _list_files(self, folder_id: str, page_size: int) -> list[dict[str, str]]:
        query = f"'{folder_id}' in parents and trashed = false"
        params = {
            "q": query,
            "fields": "files(id, name, mimeType)",
            "pageSize": str(page_size),
        }
        response = await self._api_request("GET", GDRIVE_FILES_ENDPOINT, params=params)
        if response.status != 200:
            return []
        return (await response.json()).get("files", [])

    async def list_week_files(self) -> list[tuple[dict[str, str], int]]:
        """Every readable week report in the reports folder and its subfolders.

        Returns ``(file entry, week number)`` pairs, one per week number.
        Month subfolders are read leniently because everything in them is a
        report; the root folder needs a week keyword, since anything at all can
        sit there.  The reports folder covers a single school year, so two
        files resolving to the same week means one of them is named oddly —
        the keyword-named file wins and the other is logged.
        """
        folders = await self.list_folders()
        # (files, strict): month subfolders hold reports only, the root does not.
        listings: list[tuple[list[dict[str, str]], bool]] = [
            (await self._list_files(folder.id, 50), False) for folder in folders
        ]
        listings.append((await self._list_files(self._reports_folder_id, 100), True))

        seen_ids: set[str] = set()
        found: dict[int, tuple[dict[str, str], bool]] = {}

        for files, strict in listings:
            for file in files:
                if file.get("mimeType", "") not in (
                    GOOGLE_DOCS_MIME, DOCX_MIME, "text/plain",
                ):
                    continue
                if file.get("id", "") in seen_ids:
                    continue

                name = file.get("name", "")
                week_number = self.week_number_from_name(name, strict=strict)
                if week_number is None:
                    if strict:
                        _LOGGER.debug("Skipping non-report Drive file: %s", name)
                    else:
                        _LOGGER.warning(
                            "Report file has no usable week number, skipped: %s", name,
                        )
                    continue
                seen_ids.add(file["id"])

                keyword_named = self.week_number_from_name(name) is not None
                previous = found.get(week_number)
                if previous is None:
                    found[week_number] = (file, keyword_named)
                    continue

                kept, dropped = previous[0], file
                if keyword_named and not previous[1]:
                    kept, dropped = file, previous[0]
                    found[week_number] = (file, keyword_named)
                _LOGGER.warning(
                    "Two Drive files resolve to week %d: keeping %s, ignoring %s",
                    week_number, kept.get("name", ""), dropped.get("name", ""),
                )

        return [(file, week) for week, (file, _) in sorted(found.items())]

    async def fetch_report_from_file(
        self, file_info: dict[str, str], week_number: int, school_year: str = "",
    ) -> WeeklyReport:
        """Download a report from an entry returned by :meth:`list_week_files`."""
        content = await self._get_file_content(
            file_info["id"], file_info.get("mimeType", ""),
        )
        report = WeeklyReport(
            week_number=week_number,
            content=content,
            file_name=file_info.get("name", ""),
            fetched_at=datetime.now(),
            school_year=school_year or self.school_year,
        )
        self._report_cache[(report.school_year, week_number)] = report
        return report

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
                # Everything in a month folder is a report, so odd names count.
                if self.week_number_from_name(
                    file.get("name", ""), strict=False,
                ) == week_number:
                    mime = file.get("mimeType", "")
                    if mime in (GOOGLE_DOCS_MIME, DOCX_MIME, "text/plain"):
                        return file
        return None

    async def _find_week_file_in_root(self, week_number: int) -> dict[str, str] | None:
        """Search the root reports folder for a file matching 'Week N'."""
        query = (
            f"'{self._reports_folder_id}' in parents and trashed = false "
            f"and mimeType != 'application/vnd.google-apps.folder'"
        )
        params = {"q": query, "fields": "files(id, name, mimeType)", "pageSize": "100"}
        response = await self._api_request("GET", GDRIVE_FILES_ENDPOINT, params=params)
        if response.status != 200:
            return None
        files = (await response.json()).get("files", [])
        for file in files:
            if self._matches_week_number(file.get("name", ""), week_number):
                mime = file.get("mimeType", "")
                if mime in (GOOGLE_DOCS_MIME, DOCX_MIME, "text/plain"):
                    return file
        return None

    async def get_week_report(
        self,
        week_number: int | None = None,
        target_date: date | None = None,
        school_year: str = "",
    ) -> WeeklyReport | None:
        if week_number is None:
            if target_date is None:
                target_date = date.today()
            school_start = self.school_year_start_for(target_date)
            week_number = get_school_week_number(target_date, school_start)
            school_year = school_year or school_year_label(school_start)

        school_year = school_year or self.school_year
        cache_key = (school_year, week_number)

        if cache_key in self._report_cache:
            cached = self._report_cache[cache_key]
            if datetime.now() - cached.fetched_at < timedelta(hours=1):
                return cached

        # Search month subfolders for "Week N" files
        document = await self._find_week_file_in_subfolders(week_number)

        # Search root folder for "Week N" files
        if not document:
            document = await self._find_week_file_in_root(week_number)

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
            school_year=school_year,
        )
        self._report_cache[cache_key] = report
        _LOGGER.info(
            "Fetched weekly report for %s week %d: %s",
            school_year, week_number, document["name"],
        )
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
