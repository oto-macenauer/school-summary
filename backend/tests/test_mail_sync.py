"""Tests for the mail sync module."""

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.mail import MailMessage
from app.modules.mail_sync import sync_mail_from_gdrive
from app.storage.mail_storage import MailStorage


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mail_storage(temp_dir):
    return MailStorage(temp_dir, "TestStudent")


@pytest.fixture
def mock_gdrive_client():
    client = MagicMock()
    client._api_request = AsyncMock()
    client._get_file_content = AsyncMock()
    return client


MD_CONTENT = """---
subject: Test Email
from: a@b.com
date: 2025-01-15T10:00:00
---

Body text."""


class TestSyncMailFromGdrive:
    @pytest.mark.asyncio
    async def test_syncs_new_files(self, mock_gdrive_client, mail_storage):
        list_response = AsyncMock()
        list_response.status = 200
        list_response.json = AsyncMock(return_value={
            "files": [
                {"id": "f1", "name": "email1.md", "mimeType": "text/plain"},
                {"id": "f2", "name": "email2.md", "mimeType": "text/plain"},
            ]
        })
        mock_gdrive_client._api_request.return_value = list_response
        mock_gdrive_client._get_file_content.return_value = MD_CONTENT

        count = await sync_mail_from_gdrive(mock_gdrive_client, "folder_id", mail_storage)
        assert count == 2
        assert mail_storage.message_exists("f1")
        assert mail_storage.message_exists("f2")

    @pytest.mark.asyncio
    async def test_skips_existing(self, mock_gdrive_client, mail_storage):
        msg = MailMessage("f1", "Existing", "a@b.com", datetime(2025, 1, 15), "body")
        mail_storage.save_message(msg)

        list_response = AsyncMock()
        list_response.status = 200
        list_response.json = AsyncMock(return_value={
            "files": [
                {"id": "f1", "name": "email1.md", "mimeType": "text/plain"},
            ]
        })
        mock_gdrive_client._api_request.return_value = list_response

        count = await sync_mail_from_gdrive(mock_gdrive_client, "folder_id", mail_storage)
        assert count == 0
        mock_gdrive_client._get_file_content.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_non_md_files(self, mock_gdrive_client, mail_storage):
        list_response = AsyncMock()
        list_response.status = 200
        list_response.json = AsyncMock(return_value={
            "files": [
                {"id": "f1", "name": "image.png", "mimeType": "image/png"},
                {"id": "f2", "name": "doc.pdf", "mimeType": "application/pdf"},
            ]
        })
        mock_gdrive_client._api_request.return_value = list_response

        count = await sync_mail_from_gdrive(mock_gdrive_client, "folder_id", mail_storage)
        assert count == 0
        mock_gdrive_client._get_file_content.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_api_error(self, mock_gdrive_client, mail_storage):
        error_response = AsyncMock()
        error_response.status = 500
        error_response.text = AsyncMock(return_value="Internal error")
        mock_gdrive_client._api_request.return_value = error_response

        count = await sync_mail_from_gdrive(mock_gdrive_client, "folder_id", mail_storage)
        assert count == 0

    @pytest.mark.asyncio
    async def test_handles_file_download_error(self, mock_gdrive_client, mail_storage):
        list_response = AsyncMock()
        list_response.status = 200
        list_response.json = AsyncMock(return_value={
            "files": [
                {"id": "f1", "name": "email1.md", "mimeType": "text/plain"},
                {"id": "f2", "name": "email2.md", "mimeType": "text/plain"},
            ]
        })
        mock_gdrive_client._api_request.return_value = list_response
        mock_gdrive_client._get_file_content.side_effect = [
            Exception("Download failed"),
            MD_CONTENT,
        ]

        count = await sync_mail_from_gdrive(mock_gdrive_client, "folder_id", mail_storage)
        assert count == 1
        assert not mail_storage.message_exists("f1")
        assert mail_storage.message_exists("f2")

    @pytest.mark.asyncio
    async def test_accepts_text_plain_mime(self, mock_gdrive_client, mail_storage):
        list_response = AsyncMock()
        list_response.status = 200
        list_response.json = AsyncMock(return_value={
            "files": [
                {"id": "f1", "name": "email_no_ext", "mimeType": "text/plain"},
            ]
        })
        mock_gdrive_client._api_request.return_value = list_response
        mock_gdrive_client._get_file_content.return_value = MD_CONTENT

        count = await sync_mail_from_gdrive(mock_gdrive_client, "folder_id", mail_storage)
        assert count == 1

    @pytest.mark.asyncio
    async def test_empty_folder(self, mock_gdrive_client, mail_storage):
        list_response = AsyncMock()
        list_response.status = 200
        list_response.json = AsyncMock(return_value={"files": []})
        mock_gdrive_client._api_request.return_value = list_response

        count = await sync_mail_from_gdrive(mock_gdrive_client, "folder_id", mail_storage)
        assert count == 0
