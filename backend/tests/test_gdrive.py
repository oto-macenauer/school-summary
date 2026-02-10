"""Tests for Google Drive API client."""

import json
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.gdrive import (
    GDRIVE_FILES_ENDPOINT,
    GOOGLE_DOCS_MIME,
    GOOGLE_TOKEN_ENDPOINT,
    FolderInfo,
    GoogleDriveAuthError,
    GoogleDriveClient,
    GoogleDriveError,
    GoogleDriveNotFoundError,
    WeeklyReport,
    get_school_week_number,
    get_school_year_start,
)


class TestSchoolWeekCalculation:
    """Tests for school week number calculation."""

    def test_first_week_of_school_year(self):
        """Test week 1 is the week containing September 1."""
        school_start = date(2024, 9, 1)  # Sunday
        # Monday of that week
        assert get_school_week_number(date(2024, 8, 26), school_start) == 1
        # September 1st itself
        assert get_school_week_number(date(2024, 9, 1), school_start) == 1
        # Friday of that week
        assert get_school_week_number(date(2024, 8, 30), school_start) == 1

    def test_second_week_of_school_year(self):
        """Test week 2 starts the Monday after week 1."""
        school_start = date(2024, 9, 1)
        # Monday of week 2
        assert get_school_week_number(date(2024, 9, 2), school_start) == 2
        # Friday of week 2
        assert get_school_week_number(date(2024, 9, 6), school_start) == 2

    def test_week_15(self):
        """Test calculation for week 15 (early December)."""
        school_start = date(2024, 9, 1)
        # School year starts Sept 1 (Sunday), Week 1 Monday is Aug 26
        # Week 15 starts December 2, 2024 (14 weeks after Aug 26)
        assert get_school_week_number(date(2024, 12, 2), school_start) == 15
        assert get_school_week_number(date(2024, 12, 6), school_start) == 15

    def test_school_year_start_on_monday(self):
        """Test when school year starts on a Monday."""
        school_start = date(2025, 9, 1)  # Monday
        # Week 1 is September 1-7
        assert get_school_week_number(date(2025, 9, 1), school_start) == 1
        assert get_school_week_number(date(2025, 9, 7), school_start) == 1
        # Week 2
        assert get_school_week_number(date(2025, 9, 8), school_start) == 2


class TestSchoolYearStart:
    """Tests for school year start calculation."""

    def test_during_fall_semester(self):
        """Test school year start when in fall semester."""
        # November 2024 -> school year started Sept 2024
        assert get_school_year_start(date(2024, 11, 15)) == date(2024, 9, 1)

    def test_during_spring_semester(self):
        """Test school year start when in spring semester."""
        # March 2025 -> school year started Sept 2024
        assert get_school_year_start(date(2025, 3, 15)) == date(2024, 9, 1)

    def test_in_august(self):
        """Test school year start during August."""
        # August 2024 -> school year started Sept 2023
        assert get_school_year_start(date(2024, 8, 15)) == date(2023, 9, 1)

    def test_in_september(self):
        """Test school year start during September."""
        # September 2024 -> school year started Sept 2024
        assert get_school_year_start(date(2024, 9, 15)) == date(2024, 9, 1)


class TestGoogleDriveClient:
    """Tests for GoogleDriveClient class."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock aiohttp session."""
        return MagicMock()

    @pytest.fixture
    def service_account_data(self):
        """Create mock service account data."""
        return {
            "client_email": "test@test-project.iam.gserviceaccount.com",
            "private_key": """-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEA0Z3VS5JJcds3xfn/ygWyF8PbnGy0AHB7MnMkwF7k0y5V1hHv
HEkL0OMHfnBqKjLlqzv/rAhwVyYxj5gMHJdTgP6nMrPXrbLb3KsL9j5W8yRMbgYl
sDLqVNGJbXDJb7kHwrHkMlWvdvLqFxPqFjRhnPc+gMjJGXj3AAi3TrF3eVAF1qXy
G7U0WNWnLFqZLB5U5oVUyJN8c7JnPcqT5S+RrPMPM1YzV3lJbXKlKLt5fZd9HWFH
YhfFbU3EE6xPQdH7uVqnnlCnqeQzJH1nxMbAPdrNf9vmrqbyLPdAuXHzN3hLwkVZ
Ey1fMrMJXLIYEwwH1CMIb1IHCRDKQhS9vzwQIQIDAQABAoIBABGwPpfSk0ThIJVL
Cqf3k3N9q7LKhGYNqMq0MrQdC8hC8lRl3G8LnMKUH3x7K7i4YMzYyMEBRpRj+S6m
z6r1Cl5UlR0yHcE8AAuVmPRz0hPKP8zhxkjKT8SFBqYMWuT4OOVaL0n5cXl8N6Me
qMTPhb5R8DnHzPLs8Lf7vPz7B1PjR3jJNp5gK8QKwb5LYe7B8PoLl5b7K8WKFB5Z
lW4k3v0gk1AUdjrBYF0xpvlqN9f6lF3xZsCfqg0e7jPdLCf6HrFn7PjCvvMQDLlN
+1e+2hQ9HfT8TmTJVZcvLZrX3J0N8ykYfE9lXrRLj4K3f3Y3jS3lKCK6bCGjHvPM
VK0Y4AECgYEA5l3W8t9KjJZGtLb7NQHK4q5P6R0mKH3F0zGc8fJHG3Y5eGCvYZB7
-----END RSA PRIVATE KEY-----""",
            "type": "service_account",
        }

    @pytest.fixture
    def client(self, mock_session, tmp_path, service_account_data):
        """Create a GoogleDriveClient instance."""
        # Write service account to temp file
        sa_file = tmp_path / "service_account.json"
        sa_file.write_text(json.dumps(service_account_data))

        return GoogleDriveClient(
            str(sa_file),
            "test_folder_id",
            mock_session,
            date(2024, 9, 1),
        )

    def test_init(self, client):
        """Test client initialization."""
        assert client._reports_folder_id == "test_folder_id"
        assert client._school_year_start == date(2024, 9, 1)
        assert client._access_token is None

    @pytest.mark.asyncio
    async def test_load_service_account_not_found(self, mock_session):
        """Test error when service account file not found."""
        client = GoogleDriveClient(
            "/nonexistent/path.json",
            "folder_id",
            mock_session,
        )

        with pytest.raises(GoogleDriveAuthError, match="not found"):
            await client._load_service_account()

    @pytest.mark.asyncio
    async def test_load_service_account_invalid_json(self, mock_session, tmp_path):
        """Test error when service account file has invalid JSON."""
        sa_file = tmp_path / "invalid.json"
        sa_file.write_text("not valid json")

        client = GoogleDriveClient(str(sa_file), "folder_id", mock_session)

        with pytest.raises(GoogleDriveAuthError, match="Invalid service account JSON"):
            await client._load_service_account()

    @pytest.mark.asyncio
    async def test_find_week_folder_exact_match(self, client, mock_session):
        """Test finding folder by exact week number."""
        # Mock the list_folders response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "files": [
                {"id": "folder_14", "name": "14"},
                {"id": "folder_15", "name": "15"},
                {"id": "folder_16", "name": "16"},
            ]
        })

        with patch.object(client, "_api_request", return_value=mock_response):
            folder_id = await client.find_week_folder(15)
            assert folder_id == "folder_15"

    @pytest.mark.asyncio
    async def test_find_week_folder_pattern_match(self, client, mock_session):
        """Test finding folder by pattern (Week 15, Tyden 15, etc.)."""
        # Mock the list_folders response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "files": [
                {"id": "folder_week_15", "name": "Week 15"},
                {"id": "folder_tyden_16", "name": "Týden 16"},
            ]
        })

        with patch.object(client, "_api_request", return_value=mock_response):
            folder_id = await client.find_week_folder(15)
            assert folder_id == "folder_week_15"

            folder_id = await client.find_week_folder(16)
            assert folder_id == "folder_tyden_16"

    @pytest.mark.asyncio
    async def test_find_week_folder_not_found(self, client, mock_session):
        """Test when week folder is not found."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "files": [
                {"id": "folder_14", "name": "14"},
            ]
        })

        with patch.object(client, "_api_request", return_value=mock_response):
            folder_id = await client.find_week_folder(20)
            assert folder_id is None

    @pytest.mark.asyncio
    async def test_extract_docx_text(self, client):
        """Test extracting text from DOCX content."""
        # Create a minimal DOCX-like ZIP structure
        import io
        import zipfile

        docx_buffer = io.BytesIO()
        with zipfile.ZipFile(docx_buffer, "w") as zf:
            # Create minimal document.xml
            doc_xml = """<?xml version="1.0"?>
            <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
                <w:body>
                    <w:p><w:r><w:t>Hello</w:t></w:r></w:p>
                    <w:p><w:r><w:t>World</w:t></w:r></w:p>
                </w:body>
            </w:document>"""
            zf.writestr("word/document.xml", doc_xml)

        docx_content = docx_buffer.getvalue()
        text = await client._extract_docx_text(docx_content)

        assert "Hello" in text
        assert "World" in text

    @pytest.mark.asyncio
    async def test_extract_docx_text_invalid_zip(self, client):
        """Test error when DOCX is invalid ZIP."""
        with pytest.raises(GoogleDriveError, match="Failed to parse DOCX"):
            await client._extract_docx_text(b"not a zip file")

    def test_clear_cache(self, client):
        """Test clearing the report cache."""
        # Add some cached data
        client._report_cache[15] = WeeklyReport(
            week_number=15,
            content="Test content",
            file_name="report.docx",
            fetched_at=datetime.now(),
        )

        assert len(client._report_cache) == 1

        client.clear_cache()

        assert len(client._report_cache) == 0


class TestMatchesWeekNumber:
    """Tests for week number filename matching."""

    @pytest.fixture
    def client(self, tmp_path):
        sa_file = tmp_path / "sa.json"
        sa_file.write_text('{"client_email":"x","private_key":"x"}')
        return GoogleDriveClient(str(sa_file), "fid", MagicMock(), date(2024, 9, 1))

    @pytest.mark.parametrize("filename,week,expected", [
        ("Week 14.docx", 14, True),
        ("Week 14", 14, True),
        ("week 14.docx", 14, True),
        ("Week 15.docx", 14, False),
        ("Týden 14.docx", 14, True),
        ("tyden 14.docx", 14, True),
        ("W14.docx", 14, True),
        ("w 14.docx", 14, True),
        ("Week 14.pdf", 14, True),
        ("December", 14, False),
        ("random.docx", 14, False),
        ("Week 4.docx", 4, True),
        ("Week 4.docx", 14, False),
    ])
    def test_matches(self, client, filename, week, expected):
        assert client._matches_week_number(filename, week) == expected


class TestFindWeekFileInSubfolders:
    """Tests for searching month subfolders for week files."""

    @pytest.fixture
    def client(self, tmp_path):
        sa_file = tmp_path / "sa.json"
        sa_file.write_text('{"client_email":"x","private_key":"x"}')
        return GoogleDriveClient(str(sa_file), "root_id", MagicMock(), date(2024, 9, 1))

    @pytest.mark.asyncio
    async def test_finds_week_file_in_month_folder(self, client):
        """Test finding 'Week 14.docx' inside a December subfolder."""
        DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        folders_response = AsyncMock()
        folders_response.status = 200
        folders_response.json = AsyncMock(return_value={
            "files": [
                {"id": "dec_id", "name": "December"},
                {"id": "jan_id", "name": "January"},
            ]
        })

        dec_files_response = AsyncMock()
        dec_files_response.status = 200
        dec_files_response.json = AsyncMock(return_value={
            "files": [
                {"id": "f14", "name": "Week 14.docx", "mimeType": DOCX},
                {"id": "f15", "name": "Week 15.docx", "mimeType": DOCX},
            ]
        })

        call_count = 0

        async def mock_api(method, url, params=None, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return folders_response
            return dec_files_response

        with patch.object(client, "_api_request", side_effect=mock_api):
            result = await client._find_week_file_in_subfolders(14)
            assert result is not None
            assert result["id"] == "f14"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, client):
        """Test returns None when week file doesn't exist."""
        folders_response = AsyncMock()
        folders_response.status = 200
        folders_response.json = AsyncMock(return_value={
            "files": [{"id": "dec_id", "name": "December"}]
        })

        dec_files_response = AsyncMock()
        dec_files_response.status = 200
        dec_files_response.json = AsyncMock(return_value={
            "files": [
                {"id": "f14", "name": "Week 14.docx",
                 "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
            ]
        })

        call_count = 0

        async def mock_api(method, url, params=None, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return folders_response
            return dec_files_response

        with patch.object(client, "_api_request", side_effect=mock_api):
            result = await client._find_week_file_in_subfolders(99)
            assert result is None


class TestWeeklyReport:
    """Tests for WeeklyReport dataclass."""

    def test_creation(self):
        """Test creating a WeeklyReport."""
        report = WeeklyReport(
            week_number=15,
            content="Test content for week 15",
            file_name="Week 15 Report.docx",
            fetched_at=datetime(2024, 12, 15, 10, 0, 0),
        )

        assert report.week_number == 15
        assert report.content == "Test content for week 15"
        assert report.file_name == "Week 15 Report.docx"
        assert report.fetched_at == datetime(2024, 12, 15, 10, 0, 0)


class TestFolderInfo:
    """Tests for FolderInfo dataclass."""

    def test_creation(self):
        """Test creating a FolderInfo."""
        folder = FolderInfo(id="abc123", name="Week 15")

        assert folder.id == "abc123"
        assert folder.name == "Week 15"
