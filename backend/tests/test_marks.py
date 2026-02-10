"""Tests for the marks module."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.marks import (
    Mark,
    MarksData,
    MarksModule,
    SubjectMarks,
)

from .conftest import load_fixture


@pytest.fixture
def marks_response() -> dict[str, Any]:
    """Load marks fixture."""
    return load_fixture("marks_response.json")


class TestMark:
    """Tests for Mark dataclass."""

    def test_from_api_response(self, marks_response: dict[str, Any]) -> None:
        """Test creating Mark from API response."""
        mark_data = marks_response["Subjects"][0]["Marks"][0]
        mark = Mark.from_api_response(mark_data)

        assert mark.mark_id == "M1"
        assert "rovnice" in mark.caption  # Check partial match to avoid encoding issues
        assert mark.mark_text == "1"
        assert mark.weight == 2
        assert mark.is_new is False
        assert mark.mark_date is not None

    def test_numeric_value_simple(self) -> None:
        """Test numeric value for simple grade."""
        mark = Mark(
            mark_id="1",
            mark_date=None,
            edit_date=None,
            caption="Test",
            mark_text="2",
            weight=1,
            subject_id="MAT",
            teacher_id=None,
            type_code="T",
            type_note="Test",
            is_new=False,
            is_points=False,
            points_text=None,
            max_points=None,
        )
        assert mark.numeric_value == 2.0

    def test_numeric_value_with_minus(self) -> None:
        """Test numeric value for grade with minus."""
        mark = Mark(
            mark_id="1",
            mark_date=None,
            edit_date=None,
            caption="Test",
            mark_text="2-",
            weight=1,
            subject_id="MAT",
            teacher_id=None,
            type_code="T",
            type_note="Test",
            is_new=False,
            is_points=False,
            points_text=None,
            max_points=None,
        )
        assert mark.numeric_value == 2.5

    def test_numeric_value_with_plus(self) -> None:
        """Test numeric value for grade with plus."""
        mark = Mark(
            mark_id="1",
            mark_date=None,
            edit_date=None,
            caption="Test",
            mark_text="1+",
            weight=1,
            subject_id="MAT",
            teacher_id=None,
            type_code="T",
            type_note="Test",
            is_new=False,
            is_points=False,
            points_text=None,
            max_points=None,
        )
        assert mark.numeric_value == 0.75

    def test_numeric_value_empty(self) -> None:
        """Test numeric value for empty grade."""
        mark = Mark(
            mark_id="1",
            mark_date=None,
            edit_date=None,
            caption="Test",
            mark_text="",
            weight=1,
            subject_id="MAT",
            teacher_id=None,
            type_code="T",
            type_note="Test",
            is_new=False,
            is_points=False,
            points_text=None,
            max_points=None,
        )
        assert mark.numeric_value is None

    def test_numeric_value_text_grade(self) -> None:
        """Test numeric value for text grade."""
        mark = Mark(
            mark_id="1",
            mark_date=None,
            edit_date=None,
            caption="Test",
            mark_text="N",
            weight=1,
            subject_id="MAT",
            teacher_id=None,
            type_code="T",
            type_note="Test",
            is_new=False,
            is_points=False,
            points_text=None,
            max_points=None,
        )
        assert mark.numeric_value is None


class TestSubjectMarks:
    """Tests for SubjectMarks dataclass."""

    def test_from_api_response(self, marks_response: dict[str, Any]) -> None:
        """Test creating SubjectMarks from API response."""
        subject_data = marks_response["Subjects"][0]
        subject = SubjectMarks.from_api_response(subject_data)

        assert subject.subject_name == "Matematika"
        assert subject.subject_abbrev == "M"
        assert subject.average_text == "1,75"
        assert len(subject.marks) == 2

    def test_average_parsing(self) -> None:
        """Test average parsing from text."""
        subject = SubjectMarks(
            subject_id="MAT",
            subject_name="Math",
            subject_abbrev="M",
            average_text="2,50",
            marks=[],
        )
        assert subject.average == 2.50

    def test_average_parsing_dot(self) -> None:
        """Test average parsing with dot."""
        subject = SubjectMarks(
            subject_id="MAT",
            subject_name="Math",
            subject_abbrev="M",
            average_text="2.50",
            marks=[],
        )
        assert subject.average == 2.50

    def test_average_empty(self) -> None:
        """Test average when empty."""
        subject = SubjectMarks(
            subject_id="MAT",
            subject_name="Math",
            subject_abbrev="M",
            average_text="",
            marks=[],
        )
        assert subject.average is None

    def test_new_marks_count(self) -> None:
        """Test counting new marks."""
        marks = [
            MagicMock(is_new=True),
            MagicMock(is_new=False),
            MagicMock(is_new=True),
        ]
        subject = SubjectMarks(
            subject_id="MAT",
            subject_name="Math",
            subject_abbrev="M",
            average_text="2,00",
            marks=marks,
        )
        assert subject.new_marks_count == 2

    def test_calculated_average(self) -> None:
        """Test calculated weighted average."""
        marks = [
            MagicMock(numeric_value=1.0, weight=2),
            MagicMock(numeric_value=2.0, weight=1),
        ]
        subject = SubjectMarks(
            subject_id="MAT",
            subject_name="Math",
            subject_abbrev="M",
            average_text="",
            marks=marks,
        )
        # (1*2 + 2*1) / (2+1) = 4/3 = 1.33
        assert subject.calculated_average == 1.33

    def test_latest_mark(self) -> None:
        """Test getting latest mark."""
        marks = [
            MagicMock(mark_date=datetime(2024, 12, 1)),
            MagicMock(mark_date=datetime(2024, 12, 10)),
            MagicMock(mark_date=datetime(2024, 12, 5)),
        ]
        subject = SubjectMarks(
            subject_id="MAT",
            subject_name="Math",
            subject_abbrev="M",
            average_text="",
            marks=marks,
        )
        assert subject.latest_mark.mark_date == datetime(2024, 12, 10)


class TestMarksData:
    """Tests for MarksData dataclass."""

    def test_total_new_marks(self) -> None:
        """Test total new marks count."""
        subjects = [
            MagicMock(new_marks_count=2),
            MagicMock(new_marks_count=1),
            MagicMock(new_marks_count=0),
        ]
        data = MarksData(subjects=subjects)
        assert data.total_new_marks == 3

    def test_overall_average(self) -> None:
        """Test overall average calculation."""
        subjects = [
            MagicMock(average=1.5),
            MagicMock(average=2.0),
            MagicMock(average=None),  # Should be skipped
        ]
        data = MarksData(subjects=subjects)
        assert data.overall_average == 1.75

    def test_overall_average_no_data(self) -> None:
        """Test overall average with no data."""
        data = MarksData(subjects=[])
        assert data.overall_average is None

    def test_get_subject(self) -> None:
        """Test getting subject by ID."""
        subjects = [
            MagicMock(subject_id="MAT"),
            MagicMock(subject_id="CJ"),
        ]
        data = MarksData(subjects=subjects)
        assert data.get_subject("MAT") == subjects[0]
        assert data.get_subject("XXX") is None

    def test_get_subject_by_name(self) -> None:
        """Test getting subject by name."""
        subjects = [
            MagicMock(subject_id="MAT", subject_name="Matematika"),
            MagicMock(subject_id="CJ", subject_name="Český jazyk"),
        ]
        data = MarksData(subjects=subjects)
        assert data.get_subject_by_name("matematika") == subjects[0]
        assert data.get_subject_by_name("Unknown") is None


class TestMarksModule:
    """Tests for MarksModule class."""

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        """Create mock client."""
        client = MagicMock()
        client.get = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_get_marks(
        self, mock_client: MagicMock, marks_response: dict[str, Any]
    ) -> None:
        """Test fetching marks."""
        mock_client.get.return_value = marks_response

        module = MarksModule(mock_client)
        result = await module.get_marks()

        assert isinstance(result, MarksData)
        assert len(result.subjects) == 3

    @pytest.mark.asyncio
    async def test_get_marks_subject_data(
        self, mock_client: MagicMock, marks_response: dict[str, Any]
    ) -> None:
        """Test that subject data is parsed correctly."""
        mock_client.get.return_value = marks_response

        module = MarksModule(mock_client)
        result = await module.get_marks()

        # Find Math subject
        math = result.get_subject_by_name("Matematika")
        assert math is not None
        assert len(math.marks) == 2
        assert math.average == 1.75

    @pytest.mark.asyncio
    async def test_get_new_marks_count(self, mock_client: MagicMock) -> None:
        """Test getting new marks count."""
        mock_client.get.return_value = {"Count": 5}

        module = MarksModule(mock_client)
        result = await module.get_new_marks_count()

        assert result == 5
