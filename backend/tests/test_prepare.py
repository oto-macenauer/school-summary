"""Tests for the prepare module."""

from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.modules.prepare import (
    PrepareData,
    PrepareModule,
    get_next_school_day,
    get_tomorrow,
)
from app.modules.timetable import (
    DayType,
    Lesson,
    TimetableDay,
    WeekTimetable,
)


class TestGetTomorrow:
    """Tests for get_tomorrow function."""

    def test_returns_tomorrow(self):
        """Test that get_tomorrow returns tomorrow's date."""
        tomorrow = get_tomorrow()
        expected = date.today() + timedelta(days=1)
        assert tomorrow == expected


class TestGetNextSchoolDay:
    """Tests for get_next_school_day function."""

    def test_returns_tomorrow_when_no_timetable(self):
        """Test returns tomorrow when timetable is None."""
        result = get_next_school_day(None)
        assert result == date.today() + timedelta(days=1)

    def test_returns_tomorrow_when_school_day(self):
        """Test returns tomorrow when it's a school day."""
        tomorrow = date.today() + timedelta(days=1)
        day = TimetableDay(
            date=tomorrow,
            day_type=DayType.WORK_DAY,
            day_description=None,
            lessons=[],
        )
        timetable = WeekTimetable(days=[day])
        result = get_next_school_day(timetable)
        assert result == tomorrow

    def test_finds_next_school_day_when_tomorrow_is_weekend(self):
        """Test finds next school day when tomorrow is not a school day."""
        tomorrow = date.today() + timedelta(days=1)
        day_after = date.today() + timedelta(days=2)

        day1 = TimetableDay(
            date=tomorrow,
            day_type=DayType.WEEKEND,
            day_description="Weekend",
            lessons=[],
        )
        day2 = TimetableDay(
            date=day_after,
            day_type=DayType.WORK_DAY,
            day_description=None,
            lessons=[],
        )
        timetable = WeekTimetable(days=[day1, day2])

        result = get_next_school_day(timetable)
        assert result == day_after


class TestPrepareData:
    """Tests for PrepareData dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        target_date = date(2024, 12, 18)
        generated_at = datetime(2024, 12, 17, 12, 0, 0)

        data = PrepareData(
            student_name="Test Student",
            target_date=target_date,
            preparation_text="Test preparation",
            lessons_count=5,
            messages_count=3,
            generated_at=generated_at,
        )

        result = data.to_dict()

        assert result["student_name"] == "Test Student"
        assert result["target_date"] == "2024-12-18"
        assert result["lessons_count"] == 5
        assert result["messages_count"] == 3
        assert result["generated_at"] == "2024-12-17T12:00:00"

    def test_default_period(self):
        """Test that default period is 'tomorrow'."""
        data = PrepareData(
            student_name="Test",
            target_date=date.today(),
            preparation_text="Test",
            lessons_count=0,
            messages_count=0,
        )
        assert data.period == "tomorrow"


class TestPrepareModule:
    """Tests for PrepareModule class."""

    def test_get_relevant_messages_no_storage(self):
        """Test get_relevant_messages with no storage path."""
        module = PrepareModule(None, "Test Student")
        result = module.get_relevant_messages(date.today())
        assert result == []

    def test_get_relevant_messages_empty_storage(self, tmp_path):
        """Test get_relevant_messages with empty storage directory."""
        module = PrepareModule(tmp_path, "Test Student")
        result = module.get_relevant_messages(date.today())
        assert result == []

    def test_get_relevant_messages_with_file(self, tmp_path):
        """Test get_relevant_messages reads messages from files."""
        # Create a test message file
        today = datetime.now()
        message_content = f"""---
title: Test Message
sender: Test Teacher
date: {today.isoformat()}
---
This is a test message content.
"""
        (tmp_path / "test_message.md").write_text(message_content, encoding="utf-8")

        module = PrepareModule(tmp_path, "Test Student")
        messages = module.get_relevant_messages(date.today())

        assert len(messages) == 1
        assert messages[0]["title"] == "Test Message"
        assert messages[0]["sender"] == "Test Teacher"
        assert "test message content" in messages[0]["content"].lower()

    def test_get_relevant_messages_filters_old(self, tmp_path):
        """Test that old messages are filtered out."""
        # Create an old message
        old_date = datetime.now() - timedelta(days=30)
        message_content = f"""---
title: Old Message
sender: Test Teacher
date: {old_date.isoformat()}
---
Old content.
"""
        (tmp_path / "old_message.md").write_text(message_content, encoding="utf-8")

        module = PrepareModule(tmp_path, "Test Student")
        messages = module.get_relevant_messages(date.today(), days_back=7)

        assert len(messages) == 0

    def test_format_lessons_no_timetable(self):
        """Test format_lessons with no timetable."""
        module = PrepareModule(None, "Test Student")
        text, count = module.format_lessons(None, date.today())

        assert "není k dispozici" in text
        assert count == 0

    def test_format_lessons_no_day_data(self):
        """Test format_lessons when day is not in timetable."""
        module = PrepareModule(None, "Test Student")
        timetable = WeekTimetable(days=[])

        target = date.today() + timedelta(days=1)
        text, count = module.format_lessons(timetable, target)

        assert "není k dispozici" in text
        assert count == 0

    def test_format_lessons_non_school_day(self):
        """Test format_lessons for non-school day."""
        module = PrepareModule(None, "Test Student")
        target = date.today() + timedelta(days=1)

        day = TimetableDay(
            date=target,
            day_type=DayType.HOLIDAY,
            day_description="Christmas",
            lessons=[],
        )
        timetable = WeekTimetable(days=[day])

        text, count = module.format_lessons(timetable, target)

        assert "Volno" in text
        assert "Christmas" in text
        assert count == 0

    def test_format_lessons_with_lessons(self):
        """Test format_lessons with actual lessons."""
        module = PrepareModule(None, "Test Student")
        target = date.today() + timedelta(days=1)

        lesson = Lesson(
            subject_id="1",
            subject_name="Matematika",
            subject_abbrev="M",
            teacher_id="t1",
            teacher_name="Jan Novak",
            teacher_abbrev="No",
            room_id="r1",
            room_name="Room 101",
            room_abbrev="101",
            hour_id="h1",
            begin_time="08:00",
            end_time="08:45",
            theme="Algebra",
            group_abbrev=None,
            change_description=None,
            is_changed=False,
        )

        day = TimetableDay(
            date=target,
            day_type=DayType.WORK_DAY,
            day_description=None,
            lessons=[lesson],
        )
        timetable = WeekTimetable(days=[day])

        text, count = module.format_lessons(timetable, target)

        assert "08:00-08:45" in text
        assert "Matematika" in text
        assert "(M)" in text
        assert "101" in text
        assert "No" in text
        assert "Algebra" in text
        assert count == 1

    def test_build_prompt_from_template(self):
        """Test build_prompt_from_template generates prompt from template."""
        module = PrepareModule(None, "Test Student")
        target = date.today() + timedelta(days=1)

        messages = [
            {
                "title": "Domácí úkol",
                "sender": "Učitel",
                "date": datetime.now(),
                "content": "Napište esej do pátku.",
            }
        ]

        template = (
            "Připrav přehled na {day_name} {target_date}.\n"
            "Rozvrh:\n{lessons}\n"
            "Zprávy:\n{messages}"
        )

        prompt = module.build_prompt_from_template(template, messages, None, target)

        assert "Domácí úkol" in prompt
        assert "Napište esej" in prompt

    def test_get_system_instruction(self):
        """Test get_system_instruction returns Czech instruction."""
        module = PrepareModule(None, "Test Student")
        instruction = module.get_system_instruction()

        assert "pomocník" in instruction.lower() or "rodiče" in instruction.lower()
        assert "český" in instruction.lower() or "češtin" in instruction.lower()
