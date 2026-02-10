"""Tests for LogManager service."""

from __future__ import annotations

import logging
from datetime import datetime

import pytest

from app.services.log_manager import (
    LogCategory,
    LogEntry,
    LogManager,
    MAX_ENTRIES,
)


class TestLogEntry:
    """Tests for LogEntry dataclass."""

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        entry = LogEntry(
            timestamp=datetime(2025, 1, 15, 10, 30, 0),
            category=LogCategory.AUTH,
            level="INFO",
            message="Login successful",
            student="Alice",
            details={"user_id": "123"},
        )

        result = entry.to_dict()

        assert result["category"] == "auth"
        assert result["level"] == "INFO"
        assert result["message"] == "Login successful"
        assert result["student"] == "Alice"
        assert result["details"] == {"user_id": "123"}
        assert "2025-01-15" in result["timestamp"]

    def test_to_dict_no_optional_fields(self) -> None:
        """Test conversion with no optional fields."""
        entry = LogEntry(
            timestamp=datetime.now(),
            category=LogCategory.SYSTEM,
            level="DEBUG",
            message="Test",
        )

        result = entry.to_dict()
        assert result["student"] is None
        assert result["details"] is None


class TestLogManager:
    """Tests for LogManager class."""

    @pytest.fixture
    def manager(self) -> LogManager:
        """Create a fresh LogManager instance."""
        return LogManager()

    def test_log_and_get(self, manager: LogManager) -> None:
        """Test logging and retrieving entries."""
        manager.log(LogCategory.AUTH, "INFO", "Login successful")
        manager.log(LogCategory.MARKS, "DEBUG", "Fetching marks")

        entries = manager.get_logs()

        assert len(entries) == 2
        # Newest first
        assert entries[0].category == LogCategory.MARKS
        assert entries[1].category == LogCategory.AUTH

    def test_log_with_student(self, manager: LogManager) -> None:
        """Test logging with student name."""
        manager.log(LogCategory.TIMETABLE, "INFO", "Updated", student="Alice")

        entries = manager.get_logs(student="Alice")
        assert len(entries) == 1
        assert entries[0].student == "Alice"

    def test_log_with_details(self, manager: LogManager) -> None:
        """Test logging with details."""
        manager.log(
            LogCategory.KOMENS,
            "INFO",
            "Saved messages",
            details={"count": 5},
        )

        entries = manager.get_logs()
        assert entries[0].details == {"count": 5}

    def test_filter_by_category(self, manager: LogManager) -> None:
        """Test filtering logs by category."""
        manager.log(LogCategory.AUTH, "INFO", "Login")
        manager.log(LogCategory.MARKS, "INFO", "Marks fetched")
        manager.log(LogCategory.AUTH, "ERROR", "Login failed")

        auth_entries = manager.get_logs(category=LogCategory.AUTH)
        assert len(auth_entries) == 2
        assert all(e.category == LogCategory.AUTH for e in auth_entries)

    def test_filter_by_level(self, manager: LogManager) -> None:
        """Test filtering logs by level."""
        manager.log(LogCategory.AUTH, "INFO", "Login")
        manager.log(LogCategory.AUTH, "ERROR", "Failed")
        manager.log(LogCategory.MARKS, "INFO", "Marks")

        error_entries = manager.get_logs(level="ERROR")
        assert len(error_entries) == 1
        assert error_entries[0].level == "ERROR"

    def test_filter_by_category_and_level(self, manager: LogManager) -> None:
        """Test filtering by both category and level."""
        manager.log(LogCategory.AUTH, "INFO", "Login")
        manager.log(LogCategory.AUTH, "ERROR", "Failed")
        manager.log(LogCategory.MARKS, "ERROR", "Marks failed")

        entries = manager.get_logs(category=LogCategory.AUTH, level="ERROR")
        assert len(entries) == 1
        assert entries[0].message == "Failed"

    def test_max_entries_ring_buffer(self, manager: LogManager) -> None:
        """Test that LogManager acts as a ring buffer with max entries."""
        # Fill beyond max capacity
        for i in range(MAX_ENTRIES + 100):
            manager.log(LogCategory.SYSTEM, "DEBUG", f"Message {i}")

        assert manager.count == MAX_ENTRIES

        # The oldest entries should have been dropped
        entries = manager.get_logs(limit=MAX_ENTRIES)
        # First entry (newest) should be the last one added
        assert entries[0].message == f"Message {MAX_ENTRIES + 99}"

    def test_clear(self, manager: LogManager) -> None:
        """Test clearing all log entries."""
        manager.log(LogCategory.AUTH, "INFO", "Login")
        manager.log(LogCategory.MARKS, "INFO", "Marks")

        assert manager.count == 2

        manager.clear()

        assert manager.count == 0
        assert manager.get_logs() == []

    def test_pagination_limit(self, manager: LogManager) -> None:
        """Test limit parameter in get_logs."""
        for i in range(10):
            manager.log(LogCategory.SYSTEM, "INFO", f"Message {i}")

        entries = manager.get_logs(limit=3)
        assert len(entries) == 3

    def test_pagination_offset(self, manager: LogManager) -> None:
        """Test offset parameter in get_logs."""
        for i in range(10):
            manager.log(LogCategory.SYSTEM, "INFO", f"Message {i}")

        entries = manager.get_logs(limit=3, offset=2)
        assert len(entries) == 3
        # Newest first, so offset=2 skips the 2 newest
        assert entries[0].message == "Message 7"

    def test_emit_from_logging(self, manager: LogManager) -> None:
        """Test that LogManager captures records from stdlib logging."""
        # Create a logger and attach the manager as handler
        logger = logging.getLogger("bakalari.auth")
        logger.addHandler(manager)
        logger.setLevel(logging.DEBUG)

        try:
            logger.info("Test log message from logging")

            entries = manager.get_logs()
            assert len(entries) == 1
            assert entries[0].message == "Test log message from logging"
            assert entries[0].category == LogCategory.AUTH
            assert entries[0].level == "INFO"
        finally:
            logger.removeHandler(manager)

    def test_emit_unknown_logger_maps_to_system(self, manager: LogManager) -> None:
        """Test that unknown logger names map to SYSTEM category."""
        logger = logging.getLogger("bakalari.unknown_module")
        logger.addHandler(manager)
        logger.setLevel(logging.DEBUG)

        try:
            logger.warning("Unknown module log")

            entries = manager.get_logs()
            assert len(entries) == 1
            assert entries[0].category == LogCategory.SYSTEM
        finally:
            logger.removeHandler(manager)

    def test_get_categories(self, manager: LogManager) -> None:
        """Test getting list of all categories."""
        categories = manager.get_categories()
        assert LogCategory.AUTH in categories
        assert LogCategory.MARKS in categories
        assert LogCategory.SYSTEM in categories
        assert len(categories) == len(LogCategory)

    def test_count_property(self, manager: LogManager) -> None:
        """Test count property."""
        assert manager.count == 0

        manager.log(LogCategory.AUTH, "INFO", "Login")
        assert manager.count == 1

        manager.log(LogCategory.MARKS, "INFO", "Marks")
        assert manager.count == 2
