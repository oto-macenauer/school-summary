"""Marks/grades module for Bakalari API."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..core.client import BakalariClient
from ..const import API_MARKS, API_MARKS_COUNT_NEW, API_MARKS_FINAL

_LOGGER = logging.getLogger("bakalari.marks")


@dataclass
class Mark:
    """Represents a single mark/grade."""

    mark_id: str
    mark_date: datetime | None
    edit_date: datetime | None
    caption: str
    mark_text: str
    weight: int
    subject_id: str
    teacher_id: str | None
    type_code: str
    type_note: str
    is_new: bool
    is_points: bool
    points_text: str | None
    max_points: int | None

    @property
    def numeric_value(self) -> float | None:
        """Try to convert mark to numeric value."""
        # Handle Czech grade format (1, 1-, 2+, etc.)
        mark = self.mark_text.strip()
        if not mark:
            return None

        try:
            # Direct number
            return float(mark)
        except ValueError:
            pass

        # Handle 1-, 2+, etc.
        base_grade = mark.rstrip("+-")
        try:
            base = float(base_grade)
            if mark.endswith("-"):
                return base + 0.5
            elif mark.endswith("+"):
                return base - 0.25
            return base
        except ValueError:
            return None

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> Mark:
        """Create Mark from API response."""
        mark_date = None
        if data.get("MarkDate"):
            try:
                mark_date = datetime.fromisoformat(
                    data["MarkDate"].replace("Z", "+00:00")
                )
            except ValueError:
                pass

        edit_date = None
        if data.get("EditDate"):
            try:
                edit_date = datetime.fromisoformat(
                    data["EditDate"].replace("Z", "+00:00")
                )
            except ValueError:
                pass

        return cls(
            mark_id=data.get("Id", ""),
            mark_date=mark_date,
            edit_date=edit_date,
            caption=data.get("Caption", ""),
            mark_text=data.get("MarkText", ""),
            weight=data.get("Weight", 1),
            subject_id=data.get("SubjectId", ""),
            teacher_id=data.get("TeacherId"),
            type_code=data.get("Type", ""),
            type_note=data.get("TypeNote", ""),
            is_new=data.get("IsNew", False),
            is_points=data.get("IsPoints", False),
            points_text=data.get("PointsText"),
            max_points=data.get("MaxPoints"),
        )


@dataclass
class SubjectMarks:
    """Represents all marks for a subject."""

    subject_id: str
    subject_name: str
    subject_abbrev: str
    average_text: str
    marks: list[Mark] = field(default_factory=list)

    @property
    def average(self) -> float | None:
        """Parse average from text."""
        if not self.average_text:
            return None
        try:
            # Remove any trailing characters and parse
            clean = self.average_text.strip().replace(",", ".")
            return float(clean)
        except ValueError:
            return None

    @property
    def calculated_average(self) -> float | None:
        """Calculate weighted average from marks."""
        total_weight = 0
        weighted_sum = 0.0

        for mark in self.marks:
            value = mark.numeric_value
            if value is not None:
                weighted_sum += value * mark.weight
                total_weight += mark.weight

        if total_weight == 0:
            return None

        return round(weighted_sum / total_weight, 2)

    @property
    def new_marks_count(self) -> int:
        """Count new/unread marks."""
        return sum(1 for mark in self.marks if mark.is_new)

    @property
    def latest_mark(self) -> Mark | None:
        """Get the most recent mark."""
        dated_marks = [m for m in self.marks if m.mark_date]
        if not dated_marks:
            return None
        return max(dated_marks, key=lambda m: m.mark_date)

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> SubjectMarks:
        """Create SubjectMarks from API response."""
        subject_data = data.get("Subject", {})
        marks = [Mark.from_api_response(m) for m in data.get("Marks", [])]

        return cls(
            subject_id=subject_data.get("Id", ""),
            subject_name=subject_data.get("Name", ""),
            subject_abbrev=subject_data.get("Abbrev", ""),
            average_text=data.get("AverageText", ""),
            marks=marks,
        )


@dataclass
class FinalMark:
    """Represents a final/semester mark."""

    subject_id: str
    subject_name: str
    subject_abbrev: str
    mark_text: str
    semester: str
    is_final: bool

    @property
    def numeric_value(self) -> int | None:
        """Convert final mark to numeric value."""
        try:
            return int(self.mark_text.strip())
        except ValueError:
            return None

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], subject: dict[str, Any]
    ) -> FinalMark:
        """Create FinalMark from API response."""
        return cls(
            subject_id=subject.get("Id", ""),
            subject_name=subject.get("Name", ""),
            subject_abbrev=subject.get("Abbrev", ""),
            mark_text=data.get("MarkText", ""),
            semester=data.get("Semester", ""),
            is_final=data.get("IsFinal", False),
        )


@dataclass
class MarksData:
    """Contains all marks data for a student."""

    subjects: list[SubjectMarks] = field(default_factory=list)
    final_marks: list[FinalMark] = field(default_factory=list)

    @property
    def total_new_marks(self) -> int:
        """Get total count of new marks across all subjects."""
        return sum(s.new_marks_count for s in self.subjects)

    @property
    def overall_average(self) -> float | None:
        """Calculate overall average across all subjects."""
        averages = [s.average for s in self.subjects if s.average is not None]
        if not averages:
            return None
        return round(sum(averages) / len(averages), 2)

    def get_subject(self, subject_id: str) -> SubjectMarks | None:
        """Get marks for a specific subject."""
        for subject in self.subjects:
            if subject.subject_id == subject_id:
                return subject
        return None

    def get_subject_by_name(self, name: str) -> SubjectMarks | None:
        """Get marks for a subject by name."""
        name_lower = name.lower()
        for subject in self.subjects:
            if subject.subject_name.lower() == name_lower:
                return subject
        return None

    def to_summary_dict(self) -> dict[str, Any]:
        """Convert to a summary dictionary for sensor state."""
        return {
            "overall_average": self.overall_average,
            "new_marks_count": self.total_new_marks,
            "subjects": [
                {
                    "name": s.subject_name,
                    "abbrev": s.subject_abbrev,
                    "average": s.average,
                    "marks_count": len(s.marks),
                    "new_marks": s.new_marks_count,
                    "marks": [
                        {
                            "id": m.mark_id,
                            "date": m.mark_date.isoformat() if m.mark_date else None,
                            "caption": m.caption,
                            "mark_text": m.mark_text,
                            "weight": m.weight,
                            "type_note": m.type_note,
                            "is_new": m.is_new,
                            "is_points": m.is_points,
                            "points_text": m.points_text,
                            "max_points": m.max_points,
                        }
                        for m in sorted(
                            s.marks,
                            key=lambda m: m.mark_date or datetime.min,
                            reverse=True,
                        )
                    ],
                }
                for s in self.subjects
            ],
        }


class MarksModule:
    """Module for fetching and parsing marks/grades data."""

    def __init__(self, client: BakalariClient) -> None:
        """Initialize the marks module.

        Args:
            client: Authenticated Bakalari API client
        """
        self._client = client

    async def get_marks(self) -> MarksData:
        """Get all marks for the current period.

        Returns:
            MarksData containing all subjects with their marks
        """
        response = await self._client.get(API_MARKS)
        return self._parse_marks_response(response)

    async def get_final_marks(self) -> list[FinalMark]:
        """Get final/semester marks.

        Returns:
            List of final marks
        """
        response = await self._client.get(API_MARKS_FINAL)
        return self._parse_final_marks_response(response)

    async def get_new_marks_count(self) -> int:
        """Get count of new/unread marks.

        Returns:
            Number of new marks
        """
        response = await self._client.get(API_MARKS_COUNT_NEW)
        return response.get("Count", 0)

    async def get_full_marks_data(self) -> MarksData:
        """Get all marks including final marks.

        Returns:
            MarksData with both regular and final marks
        """
        marks_data = await self.get_marks()

        try:
            final_marks = await self.get_final_marks()
            marks_data.final_marks = final_marks
        except Exception as err:
            _LOGGER.warning("Failed to fetch final marks: %s", err)

        return marks_data

    def _parse_marks_response(self, response: dict[str, Any]) -> MarksData:
        """Parse API response into MarksData.

        Args:
            response: Raw API response

        Returns:
            Parsed MarksData
        """
        subjects = []
        for subject_data in response.get("Subjects", []):
            subject_marks = SubjectMarks.from_api_response(subject_data)
            subjects.append(subject_marks)

        # Sort subjects by name
        subjects.sort(key=lambda s: s.subject_name)

        return MarksData(subjects=subjects)

    def _parse_final_marks_response(
        self, response: dict[str, Any]
    ) -> list[FinalMark]:
        """Parse final marks API response.

        Args:
            response: Raw API response

        Returns:
            List of FinalMark objects
        """
        final_marks = []

        # Build subject lookup
        subjects = {s["Id"]: s for s in response.get("Subjects", [])}

        for certificate in response.get("Certificates", []):
            for mark_data in certificate.get("Marks", []):
                subject_id = mark_data.get("SubjectId", "")
                subject = subjects.get(subject_id, {})
                final_mark = FinalMark.from_api_response(mark_data, subject)
                final_marks.append(final_mark)

        return final_marks
