"""Timetable module for Bakalari API."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any

from ..core.client import BakalariClient
from ..const import API_TIMETABLE_ACTUAL, API_TIMETABLE_PERMANENT

_LOGGER = logging.getLogger("bakalari.timetable")


class DayType(Enum):
    """Types of days in the timetable."""

    WORK_DAY = "WorkDay"
    HOLIDAY = "Holiday"
    CELEBRATION = "Celebration"
    DIRECTOR_DAY = "DirectorDay"
    WEEKEND = "Weekend"
    UNDEFINED = "Undefined"

    @classmethod
    def from_string(cls, value: str) -> DayType:
        """Create DayType from string value."""
        for member in cls:
            if member.value == value:
                return member
        return cls.UNDEFINED


@dataclass
class Lesson:
    """Represents a single lesson in the timetable."""

    subject_id: str
    subject_name: str
    subject_abbrev: str
    teacher_id: str | None
    teacher_name: str | None
    teacher_abbrev: str | None
    room_id: str | None
    room_name: str | None
    room_abbrev: str | None
    hour_id: str
    begin_time: str
    end_time: str
    theme: str | None
    group_abbrev: str | None
    change_description: str | None
    is_changed: bool

    @classmethod
    def from_api_response(
        cls,
        atom: dict[str, Any],
        subjects: dict[str, dict[str, Any]],
        teachers: dict[str, dict[str, Any]],
        rooms: dict[str, dict[str, Any]],
        hours: dict[str, dict[str, Any]],
    ) -> Lesson | None:
        """Create Lesson from API atom response."""
        subject_id = atom.get("SubjectId")
        if not subject_id:
            return None

        subject = subjects.get(subject_id, {})
        teacher_id = atom.get("TeacherId")
        teacher = teachers.get(teacher_id, {}) if teacher_id else {}
        room_id = atom.get("RoomId")
        room = rooms.get(room_id, {}) if room_id else {}
        hour_id = atom.get("HourId", "")
        hour = hours.get(hour_id, {})

        change = atom.get("Change")
        is_changed = change is not None
        change_description = change.get("Description") if change else None

        return cls(
            subject_id=subject_id,
            subject_name=subject.get("Name", ""),
            subject_abbrev=subject.get("Abbrev", ""),
            teacher_id=teacher_id,
            teacher_name=teacher.get("Name"),
            teacher_abbrev=teacher.get("Abbrev"),
            room_id=room_id,
            room_name=room.get("Name"),
            room_abbrev=room.get("Abbrev"),
            hour_id=hour_id,
            begin_time=hour.get("BeginTime", ""),
            end_time=hour.get("EndTime", ""),
            theme=atom.get("Theme"),
            group_abbrev=atom.get("GroupAbvrev"),
            change_description=change_description,
            is_changed=is_changed,
        )


@dataclass
class TimetableDay:
    """Represents a single day in the timetable."""

    date: date
    day_type: DayType
    day_description: str | None
    lessons: list[Lesson] = field(default_factory=list)

    @property
    def is_school_day(self) -> bool:
        """Check if this is a school day."""
        return self.day_type == DayType.WORK_DAY

    @property
    def subject_names(self) -> list[str]:
        """Get list of subject names for this day (chronologically ordered)."""
        return [lesson.subject_name for lesson in self.lessons]

    @property
    def subject_abbrevs(self) -> list[str]:
        """Get list of subject abbreviations for this day (chronologically ordered)."""
        return [lesson.subject_abbrev for lesson in self.lessons]

    def to_detailed_dict(self) -> dict[str, Any]:
        """Convert to detailed dictionary with full lesson information."""
        return {
            "date": self.date.isoformat(),
            "day_type": self.day_type.value,
            "description": self.day_description,
            "is_school_day": self.is_school_day,
            "lessons": [
                {
                    "abbrev": lesson.subject_abbrev,
                    "name": lesson.subject_name,
                    "begin_time": lesson.begin_time,
                    "end_time": lesson.end_time,
                    "teacher": lesson.teacher_name,
                    "room": lesson.room_abbrev,
                    "theme": lesson.theme,
                    "group": lesson.group_abbrev,
                    "is_changed": lesson.is_changed,
                    "change_description": lesson.change_description,
                }
                for lesson in self.lessons
            ],
        }


@dataclass
class WeekTimetable:
    """Represents a week's timetable."""

    days: list[TimetableDay] = field(default_factory=list)

    @property
    def school_days(self) -> list[TimetableDay]:
        """Get only school days."""
        return [day for day in self.days if day.is_school_day]

    @property
    def all_subjects(self) -> list[str]:
        """Get all unique subjects for the week."""
        subjects = set()
        for day in self.days:
            subjects.update(day.subject_names)
        return sorted(subjects)

    def get_day(self, target_date: date) -> TimetableDay | None:
        """Get timetable for a specific date."""
        for day in self.days:
            if day.date == target_date:
                return day
        return None

    def get_subject_name_mapping(self) -> dict[str, str]:
        """Get mapping of abbreviations to full subject names."""
        mapping: dict[str, str] = {}
        for day in self.days:
            for lesson in day.lessons:
                if lesson.subject_abbrev and lesson.subject_name:
                    mapping[lesson.subject_abbrev] = lesson.subject_name
        return mapping

    def to_summary_dict(self) -> dict[str, Any]:
        """Convert to a summary dictionary for sensor state."""
        return {
            "week_subjects": self.all_subjects,
            "subject_names": self.get_subject_name_mapping(),
            "days": [day.to_detailed_dict() for day in self.days],
        }


class TimetableModule:
    """Module for fetching and parsing timetable data."""

    def __init__(self, client: BakalariClient) -> None:
        """Initialize the timetable module.

        Args:
            client: Authenticated Bakalari API client
        """
        self._client = client

    async def get_actual_timetable(
        self, target_date: date | None = None
    ) -> WeekTimetable:
        """Get the actual timetable for a week.

        Args:
            target_date: Date within the week to fetch. Defaults to today.

        Returns:
            WeekTimetable containing the week's schedule
        """
        if target_date is None:
            target_date = date.today()

        params = {"date": target_date.isoformat()}
        response = await self._client.get(API_TIMETABLE_ACTUAL, params=params)

        return self._parse_timetable_response(response)

    async def get_permanent_timetable(self) -> WeekTimetable:
        """Get the permanent/base timetable.

        Returns:
            WeekTimetable containing the permanent schedule
        """
        response = await self._client.get(API_TIMETABLE_PERMANENT)
        return self._parse_timetable_response(response)

    def _parse_timetable_response(self, response: dict[str, Any]) -> WeekTimetable:
        """Parse API response into WeekTimetable.

        Args:
            response: Raw API response

        Returns:
            Parsed WeekTimetable
        """
        # Build lookup dictionaries from response
        subjects = {s["Id"]: s for s in response.get("Subjects", [])}
        teachers = {t["Id"]: t for t in response.get("Teachers", [])}
        rooms = {r["Id"]: r for r in response.get("Rooms", [])}
        hours = {h["Id"]: h for h in response.get("Hours", [])}

        days_data = response.get("Days", [])
        days: list[TimetableDay] = []

        for day_data in days_data:
            day_date_str = day_data.get("Date", "")
            try:
                day_date = datetime.fromisoformat(day_date_str.replace("Z", "+00:00")).date()
            except ValueError:
                _LOGGER.warning("Invalid date format: %s", day_date_str)
                continue

            day_type = DayType.from_string(day_data.get("DayType", ""))
            day_description = day_data.get("DayDescription")

            lessons: list[Lesson] = []
            for atom in day_data.get("Atoms", []):
                lesson = Lesson.from_api_response(
                    atom, subjects, teachers, rooms, hours
                )
                if lesson:
                    lessons.append(lesson)

            # Sort lessons by begin time
            lessons.sort(key=lambda x: x.begin_time)

            days.append(
                TimetableDay(
                    date=day_date,
                    day_type=day_type,
                    day_description=day_description,
                    lessons=lessons,
                )
            )

        # Sort days by date
        days.sort(key=lambda x: x.date)

        return WeekTimetable(days=days)
