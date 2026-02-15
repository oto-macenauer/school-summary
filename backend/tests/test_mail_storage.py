"""Tests for the mail storage module."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from app.modules.mail import MailMessage
from app.storage.mail_storage import MailStorage, _sanitize_filename


class TestSanitizeFilename:
    def test_basic(self):
        assert _sanitize_filename("hello world") == "hello world"

    def test_removes_special_chars(self):
        result = _sanitize_filename('a<b>c:d"e/f\\g|h?i*j')
        assert all(c not in result for c in '<>:"/\\|?*')

    def test_truncates(self):
        assert len(_sanitize_filename("a" * 200)) == 80

    def test_empty(self):
        assert _sanitize_filename("") == "untitled"

    def test_strips_dots_and_spaces(self):
        assert _sanitize_filename("...test...") == "test"

    def test_collapses_whitespace(self):
        assert _sanitize_filename("hello   world") == "hello world"


class TestMailStorage:
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def storage(self, temp_dir):
        return MailStorage(temp_dir, "TestStudent")

    @pytest.fixture
    def sample_msg(self):
        return MailMessage(
            file_id="gdrive_abc123",
            subject="Test Email",
            sender="test@example.com",
            date=datetime(2025, 1, 15, 10, 30),
            body="Hello world",
        )

    def test_save_and_exists(self, storage, sample_msg):
        path = storage.save_message(sample_msg)
        assert path is not None
        assert path.exists()
        assert storage.message_exists("gdrive_abc123")

    def test_no_duplicate(self, storage, sample_msg):
        storage.save_message(sample_msg)
        path2 = storage.save_message(sample_msg)
        assert path2 is None

    def test_load_index(self, storage, sample_msg, temp_dir):
        storage.save_message(sample_msg)
        new_storage = MailStorage(temp_dir, "TestStudent")
        new_storage.load_index()
        assert new_storage.message_exists("gdrive_abc123")

    def test_load_all_messages(self, storage, sample_msg):
        storage.save_message(sample_msg)
        data = storage.load_all_messages()
        assert data.total_count == 1
        assert data.messages[0].subject == "Test Email"
        assert data.messages[0].sender == "test@example.com"

    def test_save_messages_batch(self, storage):
        msgs = [
            MailMessage(f"f{i}", f"Subject {i}", "a@b.com", datetime(2025, 1, i + 1), f"Body {i}")
            for i in range(3)
        ]
        saved = storage.save_messages(msgs)
        assert saved == 3
        assert storage.message_exists("f0")
        assert storage.message_exists("f1")
        assert storage.message_exists("f2")

    def test_save_messages_skips_duplicates(self, storage, sample_msg):
        storage.save_message(sample_msg)
        msgs = [sample_msg, MailMessage("new_id", "New", "x@y.com", None, "body")]
        saved = storage.save_messages(msgs)
        assert saved == 1

    def test_get_statistics(self, storage, sample_msg):
        storage.save_message(sample_msg)
        stats = storage.get_statistics()
        assert stats["message_count"] == 1
        assert stats["total_size_bytes"] > 0
        assert stats["total_size_mb"] >= 0

    def test_empty_storage(self, storage):
        data = storage.load_all_messages()
        assert data.total_count == 0

    def test_empty_storage_statistics(self, storage):
        stats = storage.get_statistics()
        assert stats["message_count"] == 0
        assert stats["total_size_bytes"] == 0

    def test_message_without_date(self, storage):
        msg = MailMessage("no_date", "No Date", "a@b.com", None, "body text")
        path = storage.save_message(msg)
        assert path is not None
        assert "unknown" in path.name

    def test_storage_path(self, storage, temp_dir):
        assert storage.storage_path == temp_dir / "TestStudent"
