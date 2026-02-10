"""Tests for the komens storage module."""

from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.modules.komens import (
    Attachment,
    LifetimeType,
    Message,
    MessagesData,
    Sender,
)
from app.storage.komens_storage import (
    KomensStorage,
    sanitize_filename,
)


class TestSanitizeFilename:
    """Tests for sanitize_filename function."""

    def test_removes_invalid_chars(self) -> None:
        """Test removal of invalid characters."""
        result = sanitize_filename('file<>:"/\\|?*name')
        assert "<" not in result
        assert ">" not in result
        assert ":" not in result
        assert '"' not in result
        assert "/" not in result
        assert "\\" not in result
        assert "|" not in result
        assert "?" not in result
        assert "*" not in result

    def test_strips_whitespace(self) -> None:
        """Test stripping of whitespace."""
        assert sanitize_filename("  test  ") == "test"

    def test_strips_dots(self) -> None:
        """Test stripping of leading/trailing dots."""
        assert sanitize_filename("..test..") == "test"

    def test_limits_length(self) -> None:
        """Test length limiting."""
        long_name = "a" * 150
        result = sanitize_filename(long_name)
        assert len(result) == 100

    def test_empty_returns_untitled(self) -> None:
        """Test that empty string returns 'untitled'."""
        assert sanitize_filename("") == "untitled"
        assert sanitize_filename("   ") == "untitled"
        assert sanitize_filename("...") == "untitled"


class TestKomensStorage:
    """Tests for KomensStorage class."""

    @pytest.fixture
    def temp_dir(self) -> Path:
        """Create temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def storage(self, temp_dir: Path) -> KomensStorage:
        """Create storage instance."""
        return KomensStorage(temp_dir, "TestStudent")

    @pytest.fixture
    def sample_message(self) -> Message:
        """Create sample message."""
        return Message(
            message_id="MSG001",
            title="Test Message",
            text="<p>Hello World</p>",
            sent_date=datetime(2024, 12, 10, 9, 30),
            sender=Sender("T1", "teacher", "Jan Novák"),
            is_read=False,
            is_confirmed=False,
            lifetime=LifetimeType.TO_READ,
            message_type="OBECNA",
            can_confirm=False,
            can_answer=False,
            attachments=[],
        )

    def test_storage_path(self, storage: KomensStorage, temp_dir: Path) -> None:
        """Test storage path generation."""
        assert storage.storage_path == temp_dir / "TestStudent"

    def test_ensure_directory(self, storage: KomensStorage) -> None:
        """Test directory creation."""
        storage.ensure_directory()
        assert storage.storage_path.exists()
        assert storage.storage_path.is_dir()

    def test_save_message(
        self, storage: KomensStorage, sample_message: Message
    ) -> None:
        """Test saving a message."""
        path = storage.save_message(sample_message)

        assert path is not None
        assert path.exists()
        assert path.suffix == ".md"

        content = path.read_text(encoding="utf-8")
        assert "message_id: MSG001" in content
        assert "# Test Message" in content
        assert "Jan Novák" in content

    def test_save_message_no_duplicate(
        self, storage: KomensStorage, sample_message: Message
    ) -> None:
        """Test that duplicate messages are not saved."""
        path1 = storage.save_message(sample_message)
        path2 = storage.save_message(sample_message)

        assert path1 is not None
        assert path2 is None  # Should skip duplicate

    def test_save_message_overwrite(
        self, storage: KomensStorage, sample_message: Message
    ) -> None:
        """Test overwrite flag."""
        path1 = storage.save_message(sample_message)
        path2 = storage.save_message(sample_message, overwrite=True)

        assert path1 is not None
        assert path2 is not None

    def test_message_exists(
        self, storage: KomensStorage, sample_message: Message
    ) -> None:
        """Test message existence check."""
        assert storage.message_exists(sample_message) is False

        storage.save_message(sample_message)
        assert storage.message_exists(sample_message) is True

    def test_save_messages(self, storage: KomensStorage) -> None:
        """Test saving multiple messages."""
        messages = [
            Message(
                message_id=f"MSG{i:03d}",
                title=f"Test {i}",
                text="Content",
                sent_date=datetime(2024, 12, i + 1, 10, 0),
                sender=None,
                is_read=False,
                is_confirmed=False,
                lifetime=LifetimeType.TO_READ,
                message_type="OBECNA",
                can_confirm=False,
                can_answer=False,
                attachments=[],
            )
            for i in range(3)
        ]

        paths = storage.save_messages(messages)
        assert len(paths) == 3

    def test_save_all_messages(self, storage: KomensStorage) -> None:
        """Test saving all message types."""
        msg1 = Message(
            message_id="R1",
            title="Received",
            text="Text",
            sent_date=datetime(2024, 12, 10),
            sender=None,
            is_read=False,
            is_confirmed=False,
            lifetime=LifetimeType.TO_READ,
            message_type="OBECNA",
            can_confirm=False,
            can_answer=False,
            attachments=[],
        )
        msg2 = Message(
            message_id="N1",
            title="Noticeboard",
            text="Text",
            sent_date=datetime(2024, 12, 11),
            sender=None,
            is_read=False,
            is_confirmed=False,
            lifetime=LifetimeType.TO_READ,
            message_type="OBECNA",
            can_confirm=False,
            can_answer=False,
            attachments=[],
        )

        data = MessagesData(received=[msg1], noticeboard=[msg2])
        result = storage.save_all_messages(data)

        assert len(result["received"]) == 1
        assert len(result["noticeboard"]) == 1

    def test_load_index(self, storage: KomensStorage, sample_message: Message) -> None:
        """Test loading index from disk."""
        storage.save_message(sample_message)

        # Create new storage instance
        new_storage = KomensStorage(storage._base_path, "TestStudent")
        new_storage.load_index()

        assert "MSG001" in new_storage.get_saved_message_ids()

    def test_get_saved_files(
        self, storage: KomensStorage, sample_message: Message
    ) -> None:
        """Test getting list of saved files."""
        assert len(storage.get_saved_files()) == 0

        storage.save_message(sample_message)
        files = storage.get_saved_files()

        assert len(files) == 1
        assert files[0].suffix == ".md"

    def test_get_statistics(
        self, storage: KomensStorage, sample_message: Message
    ) -> None:
        """Test getting storage statistics."""
        storage.save_message(sample_message)
        stats = storage.get_statistics()

        assert stats["message_count"] == 1
        assert stats["total_size_bytes"] > 0
        assert "storage_path" in stats

    def test_filename_generation(self, storage: KomensStorage) -> None:
        """Test filename generation with special characters."""
        msg = Message(
            message_id="MSG001",
            title="Test: Special <Characters> & More",
            text="Content",
            sent_date=datetime(2024, 12, 10, 9, 30),
            sender=None,
            is_read=False,
            is_confirmed=False,
            lifetime=LifetimeType.TO_READ,
            message_type="OBECNA",
            can_confirm=False,
            can_answer=False,
            attachments=[],
        )

        path = storage.save_message(msg)
        assert path is not None
        # Filename should be valid (no special chars)
        assert ":" not in path.name or path.name.count(":") == 0

    def test_message_without_date(self, storage: KomensStorage) -> None:
        """Test saving message without date."""
        msg = Message(
            message_id="MSG001",
            title="No Date",
            text="Content",
            sent_date=None,
            sender=None,
            is_read=False,
            is_confirmed=False,
            lifetime=LifetimeType.TO_READ,
            message_type="OBECNA",
            can_confirm=False,
            can_answer=False,
            attachments=[],
        )

        path = storage.save_message(msg)
        assert path is not None
        assert "unknown" in path.name
