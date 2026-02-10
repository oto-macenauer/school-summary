"""Tests for Summary module."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from app.modules.summary import (
    SummaryData,
    MessageSummary,
    MarkSummary,
    get_current_week_range,
    get_last_week_range,
    get_next_week_range,
)


class TestGetCurrentWeekRange:
    """Tests for get_current_week_range function."""

    def test_returns_monday_to_sunday(self):
        """Test that function returns Monday to Sunday of current week."""
        week_start, week_end = get_current_week_range()

        # week_start should be Monday
        assert week_start.weekday() == 0

        # week_end should be Sunday
        assert week_end.weekday() == 6

        # Should be 6 days apart
        assert (week_end - week_start).days == 6


class TestGetLastWeekRange:
    """Tests for get_last_week_range function."""

    def test_returns_previous_week(self):
        """Test that function returns the previous week's Monday to Sunday."""
        current_start, _ = get_current_week_range()
        last_start, last_end = get_last_week_range()

        # last_start should be Monday
        assert last_start.weekday() == 0

        # last_end should be Sunday
        assert last_end.weekday() == 6

        # Should be exactly 7 days before current week
        assert (current_start - last_start).days == 7

        # Should be 6 days apart
        assert (last_end - last_start).days == 6


class TestGetNextWeekRange:
    """Tests for get_next_week_range function."""

    def test_returns_next_week(self):
        """Test that function returns the next week's Monday to Sunday."""
        current_start, _ = get_current_week_range()
        next_start, next_end = get_next_week_range()

        # next_start should be Monday
        assert next_start.weekday() == 0

        # next_end should be Sunday
        assert next_end.weekday() == 6

        # Should be exactly 7 days after current week
        assert (next_start - current_start).days == 7

        # Should be 6 days apart
        assert (next_end - next_start).days == 6


class TestSummaryData:
    """Tests for SummaryData dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        data = SummaryData(
            student_name="Alice",
            week_start=date(2025, 12, 15),
            week_end=date(2025, 12, 21),
            summary_text="Test summary",
            messages_count=3,
            marks_count=2,
            generated_at=datetime(2025, 12, 15, 10, 0, 0),
        )

        result = data.to_dict()

        assert result["student_name"] == "Alice"
        assert result["week_start"] == "2025-12-15"
        assert result["week_end"] == "2025-12-21"
        assert result["messages_count"] == 3
        assert result["marks_count"] == 2
        assert "2025-12-15" in result["generated_at"]

    def test_to_dict_week_type(self):
        """Test that week_type is included in dict."""
        data = SummaryData(
            student_name="Alice",
            week_start=date(2025, 12, 15),
            week_end=date(2025, 12, 21),
            summary_text="Test summary",
            messages_count=0,
            marks_count=0,
            week_type="last",
        )

        result = data.to_dict()
        assert result["week_type"] == "last"

    def test_default_week_type(self):
        """Test default week_type is 'current'."""
        data = SummaryData(
            student_name="Alice",
            week_start=date(2025, 12, 15),
            week_end=date(2025, 12, 21),
            summary_text="Test",
            messages_count=0,
            marks_count=0,
        )
        assert data.week_type == "current"


class TestMessageSummary:
    """Tests for MessageSummary dataclass."""

    def test_creation(self):
        """Test creating a MessageSummary."""
        msg = MessageSummary(
            title="Test zpráva",
            sender="Učitel",
            date=datetime(2025, 12, 16, 10, 0),
            text_preview="Obsah zprávy",
        )
        assert msg.title == "Test zpráva"
        assert msg.sender == "Učitel"
        assert msg.text_preview == "Obsah zprávy"

    def test_creation_with_none_date(self):
        """Test creating a MessageSummary with no date."""
        msg = MessageSummary(
            title="Test",
            sender="Sender",
            date=None,
            text_preview="Preview",
        )
        assert msg.date is None


class TestMarkSummary:
    """Tests for MarkSummary dataclass."""

    def test_creation(self):
        """Test creating a MarkSummary."""
        mark = MarkSummary(
            subject="Matematika",
            mark="1",
            caption="Test",
            date=datetime(2025, 12, 16),
            is_new=True,
        )
        assert mark.subject == "Matematika"
        assert mark.mark == "1"
        assert mark.is_new is True

    def test_creation_not_new(self):
        """Test creating a MarkSummary that is not new."""
        mark = MarkSummary(
            subject="Fyzika",
            mark="2-",
            caption="Laboratorní práce",
            date=None,
            is_new=False,
        )
        assert mark.is_new is False
        assert mark.date is None
