"""Tests for Summary module."""

from __future__ import annotations

import tempfile
from datetime import date, datetime
from pathlib import Path

import pytest

from app.modules.summary import (
    SummaryData,
    SummaryModule,
    MessageSummary,
    MarkSummary,
    get_current_week_range,
    get_last_week_range,
    get_next_week_range,
)
from app.modules.tagging import MessageTags, TemporalTag
from app.modules.timetable import DayType, Lesson, TimetableDay, WeekTimetable
from app.storage.tag_storage import TagStorage


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


class TestSummaryModuleTemporalTags:
    """Tests for temporal tag-based filtering in SummaryModule._parse_message_file."""

    @pytest.fixture
    def temp_dir(self) -> Path:
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def summary_module(self, temp_dir: Path) -> SummaryModule:
        return SummaryModule(temp_dir, "TestStudent")

    def _create_message_file(
        self, directory: Path, msg_id: str, title: str,
        msg_date: str, body: str = "Test content",
    ) -> Path:
        path = directory / f"{msg_id}.md"
        content = (
            f"---\n"
            f"message_id: {msg_id}\n"
            f"title: {title}\n"
            f"sender: Teacher\n"
            f"date: {msg_date}\n"
            f"---\n\n{body}\n"
        )
        path.write_text(content, encoding="utf-8")
        return path

    def test_tagged_message_overlapping_week(
        self, temp_dir: Path, summary_module: SummaryModule,
    ) -> None:
        """Message with temporal tag overlapping the week should be included."""
        # Message sent March 1, but about March 10 test
        path = self._create_message_file(
            temp_dir, "MSG001", "Test info", "2026-03-01T10:00:00",
        )
        tags = MessageTags(
            temporal=[TemporalTag(date_from=date(2026, 3, 10))],
            subjects=["Matematika"],
            importance=["test"],
            tagged_at=datetime(2026, 3, 8, 12, 0),
        )
        TagStorage.write_tags(path, tags)

        # Week of March 9-15
        result = summary_module._parse_message_file(
            path, date(2026, 3, 9), date(2026, 3, 15),
        )
        assert result is not None
        assert result.title == "Test info"

    def test_tagged_message_not_overlapping(
        self, temp_dir: Path, summary_module: SummaryModule,
    ) -> None:
        """Message with temporal tag NOT overlapping should be excluded."""
        path = self._create_message_file(
            temp_dir, "MSG002", "Old test", "2026-03-01T10:00:00",
        )
        tags = MessageTags(
            temporal=[TemporalTag(date_from=date(2026, 3, 3))],
            subjects=[],
            importance=["test"],
            tagged_at=datetime(2026, 3, 8, 12, 0),
        )
        TagStorage.write_tags(path, tags)

        # Week of March 9-15 — tag date is March 3, no overlap
        result = summary_module._parse_message_file(
            path, date(2026, 3, 9), date(2026, 3, 15),
        )
        assert result is None

    def test_untagged_message_excluded(
        self, temp_dir: Path, summary_module: SummaryModule,
    ) -> None:
        """Untagged messages are excluded — cannot reliably assign to a week."""
        # Message sent within the week but not tagged
        path = self._create_message_file(
            temp_dir, "MSG003", "This week", "2026-03-10T10:00:00",
        )
        result = summary_module._parse_message_file(
            path, date(2026, 3, 9), date(2026, 3, 15),
        )
        assert result is None

        # Message sent outside the week and not tagged
        path2 = self._create_message_file(
            temp_dir, "MSG004", "Last week", "2026-03-01T10:00:00",
        )
        result2 = summary_module._parse_message_file(
            path2, date(2026, 3, 9), date(2026, 3, 15),
        )
        assert result2 is None

    def test_tagged_with_date_range_overlapping(
        self, temp_dir: Path, summary_module: SummaryModule,
    ) -> None:
        """Message with a temporal date range spanning multiple weeks should appear in both."""
        path = self._create_message_file(
            temp_dir, "MSG005", "Multi-week event", "2026-03-01T10:00:00",
        )
        tags = MessageTags(
            temporal=[TemporalTag(
                date_from=date(2026, 3, 8),
                date_to=date(2026, 3, 18),
                label="project deadline",
            )],
            subjects=[],
            importance=[],
            tagged_at=datetime(2026, 3, 8, 12, 0),
        )
        TagStorage.write_tags(path, tags)

        # Should appear in week March 9-15
        result = summary_module._parse_message_file(
            path, date(2026, 3, 9), date(2026, 3, 15),
        )
        assert result is not None

        # Should also appear in week March 16-22
        result2 = summary_module._parse_message_file(
            path, date(2026, 3, 16), date(2026, 3, 22),
        )
        assert result2 is not None

        # Should NOT appear in week March 23-29
        result3 = summary_module._parse_message_file(
            path, date(2026, 3, 23), date(2026, 3, 29),
        )
        assert result3 is None


def _lesson_with_note(abbrev: str, name: str, note: str | None) -> Lesson:
    return Lesson(
        subject_id="s1", subject_name=name, subject_abbrev=abbrev,
        teacher_id=None, teacher_name=None, teacher_abbrev=None,
        room_id=None, room_name=None, room_abbrev=None,
        hour_id="1", begin_time="08:00", end_time="08:45",
        note=note, group_abbrev=None,
        change_description=None, is_changed=False,
    )


def _week_with_notes() -> WeekTimetable:
    """Monday with two recorded notes, Tuesday with none, Wednesday a holiday."""
    return WeekTimetable(days=[
        TimetableDay(
            date=date(2026, 9, 21), day_type=DayType.WORK_DAY, day_description=None,
            lessons=[
                _lesson_with_note("M", "Matematika", "Sčítání do 100"),
                _lesson_with_note("ČJ", "Čeština", "Vyjmenovaná slova"),
            ],
        ),
        TimetableDay(
            date=date(2026, 9, 22), day_type=DayType.WORK_DAY, day_description=None,
            lessons=[_lesson_with_note("AJ", "Angličtina", None)],
        ),
        TimetableDay(
            date=date(2026, 9, 23), day_type=DayType.HOLIDAY,
            day_description="Ředitelské volno", lessons=[],
        ),
    ])


class TestFormatTimetableNotes:
    """Tests for lesson notes in the formatted timetable."""

    def test_notes_included_by_default(self):
        """Test that recorded notes are listed under their day."""
        module = SummaryModule(None, "Test")
        text = module.format_timetable(_week_with_notes())

        assert "Pondělí (21.09.): M, ČJ" in text
        assert "· probráno – M: Sčítání do 100" in text
        assert "· probráno – ČJ: Vyjmenovaná slova" in text

    def test_notes_can_be_disabled(self):
        """Test that notes can be left out."""
        module = SummaryModule(None, "Test")
        text = module.format_timetable(_week_with_notes(), include_notes=False)

        assert "Pondělí (21.09.): M, ČJ" in text
        assert "probráno" not in text

    def test_non_school_day_unchanged(self):
        """Test that non-school days keep their description."""
        module = SummaryModule(None, "Test")
        text = module.format_timetable(_week_with_notes())

        assert "- Středa: Ředitelské volno" in text

    def test_format_lesson_notes(self):
        """Test the standalone notes block."""
        module = SummaryModule(None, "Test")
        text = module.format_lesson_notes(_week_with_notes())

        assert "- Pondělí (21.09.):" in text
        assert "· M: Sčítání do 100" in text
        assert "· ČJ: Vyjmenovaná slova" in text
        # Days without notes are skipped
        assert "Úterý" not in text

    def test_format_lesson_notes_empty(self):
        """Test the notes block when no note was recorded."""
        module = SummaryModule(None, "Test")
        week = WeekTimetable(days=[
            TimetableDay(
                date=date(2026, 9, 21), day_type=DayType.WORK_DAY, day_description=None,
                lessons=[_lesson_with_note("M", "Matematika", None)],
            ),
        ])
        assert module.format_lesson_notes(week) == "Učitelé zatím nezapsali probranou látku."

    def test_format_lesson_notes_no_timetable(self):
        """Test the notes block without a timetable."""
        module = SummaryModule(None, "Test")
        assert module.format_lesson_notes(None) == "Poznámky k hodinám nejsou k dispozici."

    def test_prompt_template_lesson_notes_variable(self):
        """Test that {lesson_notes} is filled in prompt templates."""
        module = SummaryModule(None, "Test")
        prompt = module.build_prompt_from_template(
            template=(
                "Rozvrh:\n{timetable}\n\nProbrano:\n{lesson_notes}"
            ),
            messages=[],
            timetable=_week_with_notes(),
            marks=[],
            week_start=date(2026, 9, 21),
            week_end=date(2026, 9, 27),
            week_type="last",
        )

        assert "Probrano:" in prompt
        assert "· M: Sčítání do 100" in prompt
        assert "· probráno – ČJ: Vyjmenovaná slova" in prompt
