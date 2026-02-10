"""Tests for the timetable module."""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.timetable import (
    DayType,
    Lesson,
    TimetableDay,
    TimetableModule,
    WeekTimetable,
)

from .conftest import load_fixture


@pytest.fixture
def timetable_response() -> dict[str, Any]:
    """Load timetable fixture."""
    return load_fixture("timetable_response.json")


class TestDayType:
    """Tests for DayType enum."""

    def test_from_string_work_day(self) -> None:
        """Test parsing WorkDay."""
        assert DayType.from_string("WorkDay") == DayType.WORK_DAY

    def test_from_string_holiday(self) -> None:
        """Test parsing Holiday."""
        assert DayType.from_string("Holiday") == DayType.HOLIDAY

    def test_from_string_weekend(self) -> None:
        """Test parsing Weekend."""
        assert DayType.from_string("Weekend") == DayType.WEEKEND

    def test_from_string_unknown(self) -> None:
        """Test parsing unknown value."""
        assert DayType.from_string("Unknown") == DayType.UNDEFINED


class TestLesson:
    """Tests for Lesson dataclass."""

    def test_from_api_response(self, timetable_response: dict[str, Any]) -> None:
        """Test creating Lesson from API response."""
        subjects = {s["Id"]: s for s in timetable_response["Subjects"]}
        teachers = {t["Id"]: t for t in timetable_response["Teachers"]}
        rooms = {r["Id"]: r for r in timetable_response["Rooms"]}
        hours = {h["Id"]: h for h in timetable_response["Hours"]}

        atom = timetable_response["Days"][0]["Atoms"][0]
        lesson = Lesson.from_api_response(atom, subjects, teachers, rooms, hours)

        assert lesson is not None
        assert lesson.subject_name == "Matematika"
        assert lesson.subject_abbrev == "M"
        assert lesson.teacher_name == "Jan Novák"
        assert lesson.room_name == "Učebna 101"
        assert lesson.begin_time == "08:00"
        assert lesson.end_time == "08:45"
        assert lesson.is_changed is False

    def test_from_api_response_with_change(
        self, timetable_response: dict[str, Any]
    ) -> None:
        """Test creating Lesson with change."""
        subjects = {s["Id"]: s for s in timetable_response["Subjects"]}
        teachers = {t["Id"]: t for t in timetable_response["Teachers"]}
        rooms = {r["Id"]: r for r in timetable_response["Rooms"]}
        hours = {h["Id"]: h for h in timetable_response["Hours"]}

        # Day 2, Atom 2 has a change
        atom = timetable_response["Days"][1]["Atoms"][1]
        lesson = Lesson.from_api_response(atom, subjects, teachers, rooms, hours)

        assert lesson is not None
        assert lesson.is_changed is True
        assert lesson.change_description == "Supplování"

    def test_from_api_response_no_subject(self) -> None:
        """Test that atom without subject returns None."""
        atom = {"HourId": "1"}
        lesson = Lesson.from_api_response(atom, {}, {}, {}, {})
        assert lesson is None


class TestTimetableDay:
    """Tests for TimetableDay dataclass."""

    def test_is_school_day_true(self) -> None:
        """Test is_school_day for work day."""
        day = TimetableDay(
            date=date(2024, 12, 9),
            day_type=DayType.WORK_DAY,
            day_description=None,
            lessons=[],
        )
        assert day.is_school_day is True

    def test_is_school_day_false_for_holiday(self) -> None:
        """Test is_school_day for holiday."""
        day = TimetableDay(
            date=date(2024, 12, 25),
            day_type=DayType.HOLIDAY,
            day_description="Vánoční prázdniny",
            lessons=[],
        )
        assert day.is_school_day is False

    def test_subject_names(self) -> None:
        """Test getting subject names."""
        lessons = [
            MagicMock(subject_name="Math", subject_abbrev="M"),
            MagicMock(subject_name="English", subject_abbrev="E"),
        ]
        day = TimetableDay(
            date=date(2024, 12, 9),
            day_type=DayType.WORK_DAY,
            day_description=None,
            lessons=lessons,
        )
        assert day.subject_names == ["Math", "English"]


class TestWeekTimetable:
    """Tests for WeekTimetable dataclass."""

    def test_school_days(self) -> None:
        """Test filtering school days."""
        days = [
            TimetableDay(date(2024, 12, 9), DayType.WORK_DAY, None, []),
            TimetableDay(date(2024, 12, 10), DayType.WORK_DAY, None, []),
            TimetableDay(date(2024, 12, 11), DayType.HOLIDAY, "Holiday", []),
            TimetableDay(date(2024, 12, 14), DayType.WEEKEND, None, []),
        ]
        week = WeekTimetable(days=days)

        assert len(week.school_days) == 2
        assert all(d.is_school_day for d in week.school_days)

    def test_get_day(self) -> None:
        """Test getting specific day."""
        target = date(2024, 12, 10)
        days = [
            TimetableDay(date(2024, 12, 9), DayType.WORK_DAY, None, []),
            TimetableDay(target, DayType.WORK_DAY, None, []),
        ]
        week = WeekTimetable(days=days)

        found = week.get_day(target)
        assert found is not None
        assert found.date == target

    def test_get_day_not_found(self) -> None:
        """Test getting non-existent day."""
        week = WeekTimetable(days=[])
        assert week.get_day(date(2024, 12, 9)) is None

    def test_to_summary_dict(self) -> None:
        """Test conversion to summary dict."""
        lesson = MagicMock(subject_name="Math", subject_abbrev="M")
        days = [
            TimetableDay(date(2024, 12, 9), DayType.WORK_DAY, None, [lesson]),
        ]
        week = WeekTimetable(days=days)

        summary = week.to_summary_dict()
        assert "week_subjects" in summary
        assert "days" in summary
        assert len(summary["days"]) == 1


class TestTimetableModule:
    """Tests for TimetableModule class."""

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        """Create mock client."""
        client = MagicMock()
        client.get = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_get_actual_timetable(
        self, mock_client: MagicMock, timetable_response: dict[str, Any]
    ) -> None:
        """Test fetching actual timetable."""
        mock_client.get.return_value = timetable_response

        module = TimetableModule(mock_client)
        result = await module.get_actual_timetable()

        assert isinstance(result, WeekTimetable)
        assert len(result.days) == 4
        mock_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_actual_timetable_with_date(
        self, mock_client: MagicMock, timetable_response: dict[str, Any]
    ) -> None:
        """Test fetching timetable for specific date."""
        mock_client.get.return_value = timetable_response
        target_date = date(2024, 12, 9)

        module = TimetableModule(mock_client)
        await module.get_actual_timetable(target_date)

        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args
        assert call_args[1]["params"]["date"] == "2024-12-09"

    @pytest.mark.asyncio
    async def test_parse_timetable_lessons(
        self, mock_client: MagicMock, timetable_response: dict[str, Any]
    ) -> None:
        """Test that lessons are parsed correctly."""
        mock_client.get.return_value = timetable_response

        module = TimetableModule(mock_client)
        result = await module.get_actual_timetable()

        # First day should have 3 lessons
        work_days = [d for d in result.days if d.day_type == DayType.WORK_DAY]
        assert len(work_days[0].lessons) == 3

        # Check first lesson
        first_lesson = work_days[0].lessons[0]
        assert first_lesson.subject_name == "Matematika"
