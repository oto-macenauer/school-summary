"""Tests for prompt variable resolver."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.modules.marks import Mark, MarksData, SubjectMarks
from app.modules.komens import Message, MessagesData, Sender
from app.modules.summary import SummaryData, SummaryModule, MessageSummary
from app.modules.prepare import PrepareData, PrepareModule
from app.modules.timetable import DayType, Lesson, TimetableDay, WeekTimetable
from app.services.prompt_variables import (
    get_available_variables,
    resolve_prompt,
    _resolve_variable,
)
from app.storage.gdrive_storage import GDriveStorage


# --- Fixtures ---


def _make_mark(text="2", caption="Test", date_=None, weight=1, is_new=False):
    return Mark(
        mark_id="m1", mark_date=date_ or datetime(2025, 1, 15),
        edit_date=None, caption=caption, mark_text=text, weight=weight,
        subject_id="s1", teacher_id=None, type_code="N", type_note="",
        is_new=is_new, is_points=False, points_text=None, max_points=None,
    )


def _make_subject(name="Čeština", abbrev="Čj", marks=None, average="2.50"):
    return SubjectMarks(
        subject_id="s1", subject_name=name, subject_abbrev=abbrev,
        average_text=average, marks=marks or [_make_mark()],
    )


def _make_marks_data(subjects=None):
    return MarksData(subjects=subjects or [
        _make_subject("Čeština", "Čj"),
        _make_subject("Matematika", "Ma", average="1.80"),
    ])


def _make_lesson(name="Čeština", abbrev="Čj"):
    return Lesson(
        subject_id="s1", subject_name=name, subject_abbrev=abbrev,
        teacher_id=None, teacher_name="Novák", teacher_abbrev="No",
        room_id=None, room_name="101", room_abbrev="101",
        hour_id="1", begin_time="08:00", end_time="08:45",
        theme=None, group_abbrev=None,
        change_description=None, is_changed=False,
    )


def _make_timetable():
    today = date.today()
    day = TimetableDay(
        date=today, day_type=DayType.WORK_DAY, day_description=None,
        lessons=[_make_lesson("Čeština", "Čj"), _make_lesson("Matematika", "Ma")],
    )
    return WeekTimetable(days=[day])


def _make_summary(week_type="current"):
    return SummaryData(
        student_name="Test", week_start=date(2025, 1, 13),
        week_end=date(2025, 1, 19), summary_text="Shrnutí textu.",
        messages_count=5, marks_count=3, week_type=week_type,
    )


def _make_prepare(period="tomorrow"):
    return PrepareData(
        student_name="Test", target_date=date(2025, 1, 15),
        preparation_text="Příprava textu.", lessons_count=5,
        messages_count=3, period=period,
    )


@pytest.fixture
def mock_ctx(tmp_path):
    """Create a mock StudentContext with test data."""
    ctx = MagicMock()
    ctx.name = "TestStudent"
    ctx.marks = _make_marks_data()
    ctx.timetable = _make_timetable()
    ctx.komens = None
    ctx.summary_current = _make_summary("current")
    ctx.summary_last = _make_summary("last")
    ctx.summary_next = _make_summary("next")
    ctx.prepare_today = _make_prepare("today")
    ctx.prepare_tomorrow = _make_prepare("tomorrow")

    # Real SummaryModule with no storage
    ctx.summary_module = SummaryModule(None, "TestStudent")

    # Real PrepareModule with no storage
    ctx.prepare_module = PrepareModule(None, "TestStudent")

    # GDrive storage
    gdrive_path = tmp_path / "gdrive"
    ctx.gdrive_storage = GDriveStorage(gdrive_path, "TestStudent")

    return ctx


# --- Tests: resolve_prompt ---


class TestResolvePrompt:
    def test_no_variables(self, mock_ctx):
        result, resolved = resolve_prompt("Hello world", mock_ctx)
        assert result == "Hello world"
        assert resolved == []

    def test_single_variable(self, mock_ctx):
        result, resolved = resolve_prompt("Známky: {marks}", mock_ctx)
        assert "Čeština" in result
        assert "Matematika" in result
        assert "marks" in resolved

    def test_multiple_variables(self, mock_ctx):
        result, resolved = resolve_prompt("{marks} a {timetable}", mock_ctx)
        assert "Čeština" in result
        assert len(resolved) == 2
        assert "marks" in resolved
        assert "timetable" in resolved

    def test_unknown_variable_left_as_is(self, mock_ctx):
        result, resolved = resolve_prompt("Foo {unknown_var} bar", mock_ctx)
        assert "{unknown_var}" in result
        assert resolved == []

    def test_mixed_known_and_unknown(self, mock_ctx):
        result, resolved = resolve_prompt("{marks} and {foo}", mock_ctx)
        assert "Čeština" in result
        assert "{foo}" in result
        assert len(resolved) == 1

    def test_variable_with_surrounding_text(self, mock_ctx):
        result, resolved = resolve_prompt("Toto jsou známky:\n{marks}\nKonec.", mock_ctx)
        assert result.startswith("Toto jsou známky:\n")
        assert result.endswith("\nKonec.")
        assert "marks" in resolved

    def test_empty_prompt(self, mock_ctx):
        result, resolved = resolve_prompt("", mock_ctx)
        assert result == ""
        assert resolved == []


# --- Tests: individual resolvers ---


class TestResolveTimetable:
    def test_full_timetable(self, mock_ctx):
        val = _resolve_variable("timetable", mock_ctx)
        assert val is not None
        assert "Čj" in val or "Čeština" in val

    def test_today(self, mock_ctx):
        val = _resolve_variable("timetable:today", mock_ctx)
        assert val is not None

    def test_tomorrow(self, mock_ctx):
        val = _resolve_variable("timetable:tomorrow", mock_ctx)
        assert val is not None

    def test_no_timetable(self, mock_ctx):
        mock_ctx.timetable = None
        val = _resolve_variable("timetable", mock_ctx)
        assert "není k dispozici" in val


class TestResolveMarks:
    def test_all_marks(self, mock_ctx):
        val = _resolve_variable("marks", mock_ctx)
        assert "Čeština" in val
        assert "Matematika" in val

    def test_subject_by_name(self, mock_ctx):
        val = _resolve_variable("marks:Čeština", mock_ctx)
        assert "Čeština" in val
        assert "Matematika" not in val

    def test_subject_by_abbrev(self, mock_ctx):
        val = _resolve_variable("marks:čj", mock_ctx)
        assert "Čeština" in val

    def test_subject_not_found(self, mock_ctx):
        val = _resolve_variable("marks:Biologie", mock_ctx)
        assert "nenalezen" in val

    def test_new_marks_none(self, mock_ctx):
        val = _resolve_variable("marks:new", mock_ctx)
        assert "nové" in val.lower()

    def test_new_marks_present(self, mock_ctx):
        mock_ctx.marks.subjects[0].marks = [
            _make_mark(text="1", caption="Test", is_new=True),
        ]
        val = _resolve_variable("marks:new", mock_ctx)
        assert "Čeština" in val

    def test_no_marks_data(self, mock_ctx):
        mock_ctx.marks = None
        val = _resolve_variable("marks", mock_ctx)
        assert "k dispozici" in val


class TestResolveKomens:
    def test_default_no_messages(self, mock_ctx):
        val = _resolve_variable("komens", mock_ctx)
        assert "zprávy" in val.lower() or "žádné" in val.lower()

    def test_unread_no_komens(self, mock_ctx):
        val = _resolve_variable("komens:unread", mock_ctx)
        assert "zprávy" in val.lower() or "žádné" in val.lower()

    def test_last_n(self, mock_ctx):
        val = _resolve_variable("komens:last:5", mock_ctx)
        assert val is not None


class TestResolveGdrive:
    def test_latest_empty(self, mock_ctx):
        val = _resolve_variable("gdrive:latest", mock_ctx)
        assert "report" in val.lower() or "žádný" in val.lower()

    def test_week_number(self, mock_ctx):
        val = _resolve_variable("gdrive:w10", mock_ctx)
        assert "týden 10" in val.lower() or "report" in val.lower()

    def test_current(self, mock_ctx):
        val = _resolve_variable("gdrive:current", mock_ctx)
        assert val is not None

    def test_with_stored_report(self, mock_ctx):
        from app.core.gdrive import WeeklyReport
        report = WeeklyReport(
            week_number=10, content="Test report content",
            file_name="Week 10.docx", fetched_at=datetime.now(),
        )
        mock_ctx.gdrive_storage.save_report(report, "2024/2025")
        val = _resolve_variable("gdrive:w10", mock_ctx)
        assert "Test report content" in val


class TestResolveSummary:
    def test_current(self, mock_ctx):
        val = _resolve_variable("summary:current", mock_ctx)
        assert val == "Shrnutí textu."

    def test_last(self, mock_ctx):
        val = _resolve_variable("summary:last", mock_ctx)
        assert val == "Shrnutí textu."

    def test_next(self, mock_ctx):
        val = _resolve_variable("summary:next", mock_ctx)
        assert val == "Shrnutí textu."

    def test_default_is_current(self, mock_ctx):
        val = _resolve_variable("summary", mock_ctx)
        assert val == "Shrnutí textu."

    def test_missing_summary(self, mock_ctx):
        mock_ctx.summary_current = None
        val = _resolve_variable("summary:current", mock_ctx)
        assert "není k dispozici" in val


class TestResolvePrepare:
    def test_today(self, mock_ctx):
        val = _resolve_variable("prepare:today", mock_ctx)
        assert val == "Příprava textu."

    def test_tomorrow(self, mock_ctx):
        val = _resolve_variable("prepare:tomorrow", mock_ctx)
        assert val == "Příprava textu."

    def test_default_is_tomorrow(self, mock_ctx):
        val = _resolve_variable("prepare", mock_ctx)
        assert val == "Příprava textu."

    def test_missing_prepare(self, mock_ctx):
        mock_ctx.prepare_today = None
        val = _resolve_variable("prepare:today", mock_ctx)
        assert "není k dispozici" in val


# --- Tests: get_available_variables ---


class TestGetAvailableVariables:
    def test_returns_base_variables(self, mock_ctx):
        variables = get_available_variables(mock_ctx)
        names = [v["name"] for v in variables]
        assert "timetable" in names
        assert "marks" in names
        assert "komens" in names
        assert "gdrive:current" in names
        assert "summary:current" in names
        assert "prepare:today" in names

    def test_includes_subject_variables(self, mock_ctx):
        variables = get_available_variables(mock_ctx)
        names = [v["name"] for v in variables]
        assert "marks:čj" in names
        assert "marks:ma" in names

    def test_includes_gdrive_weeks(self, mock_ctx):
        from app.core.gdrive import WeeklyReport
        report = WeeklyReport(
            week_number=5, content="Content",
            file_name="Week 5.docx", fetched_at=datetime.now(),
        )
        mock_ctx.gdrive_storage.save_report(report, "2024/2025")
        variables = get_available_variables(mock_ctx)
        names = [v["name"] for v in variables]
        assert "gdrive:w5" in names

    def test_no_marks_no_subject_variables(self, mock_ctx):
        mock_ctx.marks = None
        variables = get_available_variables(mock_ctx)
        names = [v["name"] for v in variables]
        assert "marks:čj" not in names
        # Base marks variable still present
        assert "marks" in names

    def test_all_have_required_fields(self, mock_ctx):
        variables = get_available_variables(mock_ctx)
        for v in variables:
            assert "name" in v
            assert "category" in v
            assert "description" in v

    def test_categories_are_valid(self, mock_ctx):
        variables = get_available_variables(mock_ctx)
        valid = {"timetable", "marks", "komens", "gdrive", "summary", "prepare"}
        for v in variables:
            assert v["category"] in valid


# --- Tests: edge cases ---


class TestEdgeCases:
    def test_unknown_category(self, mock_ctx):
        val = _resolve_variable("weather:today", mock_ctx)
        assert val is None

    def test_empty_expression(self, mock_ctx):
        val = _resolve_variable("", mock_ctx)
        assert val is None

    def test_whitespace_in_expression(self, mock_ctx):
        result, resolved = resolve_prompt("{ marks }", mock_ctx)
        assert "marks" in resolved

    def test_nested_braces_ignored(self, mock_ctx):
        result, resolved = resolve_prompt("{{marks}}", mock_ctx)
        # The outer braces remain, inner resolved
        assert "marks" in resolved

    def test_colon_params_with_spaces(self, mock_ctx):
        val = _resolve_variable("marks : Čeština", mock_ctx)
        assert "Čeština" in val
