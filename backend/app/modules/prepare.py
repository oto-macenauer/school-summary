"""Prepare module for today/tomorrow preparation summary."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .timetable import WeekTimetable

_LOGGER = logging.getLogger("bakalari.prepare")


@dataclass
class PrepareData:
    """Contains generated preparation data."""
    student_name: str
    target_date: date
    preparation_text: str
    lessons_count: int
    messages_count: int
    period: str = "tomorrow"  # "today" or "tomorrow"
    generated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "student_name": self.student_name,
            "target_date": self.target_date.isoformat(),
            "period": self.period,
            "lessons_count": self.lessons_count,
            "messages_count": self.messages_count,
            "generated_at": self.generated_at.isoformat(),
        }


def get_tomorrow() -> date:
    return date.today() + timedelta(days=1)


def get_next_school_day(timetable: WeekTimetable | None) -> date:
    tomorrow = get_tomorrow()
    if timetable is None:
        return tomorrow
    tomorrow_data = timetable.get_day(tomorrow)
    if tomorrow_data and tomorrow_data.is_school_day:
        return tomorrow
    for day in timetable.days:
        if day.date > date.today() and day.is_school_day:
            return day.date
    return tomorrow


class PrepareModule:
    """Module for building preparation prompts for today and tomorrow."""

    def __init__(self, storage_path: Path | None, student_name: str) -> None:
        self._storage_path = storage_path
        self._student_name = student_name

    def get_relevant_messages(
        self, target_date: date, days_back: int = 14,
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        if not self._storage_path or not self._storage_path.exists():
            return messages
        cutoff_date = date.today() - timedelta(days=days_back)
        for md_file in self._storage_path.glob("*.md"):
            try:
                message = self._parse_message_file(md_file, cutoff_date)
                if message:
                    messages.append(message)
            except Exception as err:
                _LOGGER.warning("Failed to parse message file %s: %s", md_file, err)
        messages.sort(key=lambda m: m.get("date") or datetime.min, reverse=True)
        return messages

    def _parse_message_file(
        self, file_path: Path, cutoff_date: date,
    ) -> dict[str, Any] | None:
        content = file_path.read_text(encoding="utf-8")
        title = self._extract_metadata(content, "title") or "Bez názvu"
        sender = self._extract_metadata(content, "sender") or "Neznámý"
        date_str = self._extract_metadata(content, "date")
        message_date: datetime | None = None
        if date_str:
            try:
                message_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except ValueError:
                pass
        if message_date and message_date.date() < cutoff_date:
            return None
        text_content = self._extract_text_content(content)
        return {
            "title": title, "sender": sender, "date": message_date,
            "content": text_content[:1500] if text_content else "",
        }

    def _extract_metadata(self, content: str, key: str) -> str | None:
        pattern = rf"^{key}:\s*(.+)$"
        match = re.search(pattern, content, re.MULTILINE)
        return match.group(1).strip() if match else None

    def _extract_text_content(self, content: str) -> str:
        parts = content.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
        return content.strip()

    def format_lessons(
        self, timetable: WeekTimetable | None, target_date: date,
    ) -> tuple[str, int]:
        if timetable is None:
            return "Rozvrh není k dispozici.", 0
        day = timetable.get_day(target_date)
        if day is None:
            return f"Rozvrh pro {target_date.strftime('%d.%m.%Y')} není k dispozici.", 0
        if not day.is_school_day:
            return f"Volno: {day.day_description}" if day.day_description else "Volno (víkend nebo svátek)", 0
        if not day.lessons:
            return "Žádné hodiny v rozvrhu.", 0
        lines = []
        for lesson in day.lessons:
            line = f"- {lesson.begin_time}-{lesson.end_time}: {lesson.subject_name} ({lesson.subject_abbrev})"
            if lesson.room_abbrev:
                line += f" v {lesson.room_abbrev}"
            if lesson.teacher_abbrev:
                line += f" ({lesson.teacher_abbrev})"
            if lesson.theme:
                line += f" - téma: {lesson.theme}"
            if lesson.is_changed and lesson.change_description:
                line += f" [ZMĚNA: {lesson.change_description}]"
            lines.append(line)
        return "\n".join(lines), len(day.lessons)

    def format_messages(self, messages: list[dict[str, Any]]) -> str:
        """Format messages for prompt template."""
        if not messages:
            return "Žádné zprávy k dispozici."
        return "\n".join(
            f"- [{m['date'].strftime('%d.%m.%Y') if m.get('date') else '?'}] "
            f"{m['title']} (od: {m['sender']}):\n  {m['content'][:800]}"
            for m in messages[:15]
        )

    def build_prompt_from_template(
        self,
        template: str,
        messages: list[dict[str, Any]],
        timetable: WeekTimetable | None,
        target_date: date,
    ) -> str:
        """Build prompt from a config template using str.format_map()."""
        day_names = {
            0: "pondělí", 1: "úterý", 2: "středa", 3: "čtvrtek",
            4: "pátek", 5: "sobota", 6: "neděle",
        }
        lessons_text, _ = self.format_lessons(timetable, target_date)
        variables = {
            "target_date": target_date.strftime("%d.%m.%Y"),
            "day_name": day_names.get(target_date.weekday(), ""),
            "lessons": lessons_text,
            "messages": self.format_messages(messages),
        }
        try:
            return template.format_map(variables)
        except KeyError as e:
            _LOGGER.warning("Unknown template variable: %s", e)
            return template

    def get_system_instruction(self) -> str:
        return (
            "Jsi pomocník pro rodiče a žáky, který připravuje přehled toho, co je třeba "
            "nachystat do školy. Piš stručně, jasně a věcně v češtině. "
            "Zaměř se na praktické informace: co zabalit, co se naučit, jaké úkoly odevzdat."
        )
