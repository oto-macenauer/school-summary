"""Summary module for aggregating school data and building prompts."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .marks import MarksData
from .timetable import WeekTimetable

_LOGGER = logging.getLogger("bakalari.summary")


@dataclass
class MessageSummary:
    """Summary of a Komens message."""
    title: str
    sender: str
    date: datetime | None
    text_preview: str


@dataclass
class MarkSummary:
    """Summary of a mark/grade."""
    subject: str
    mark: str
    caption: str
    date: datetime | None
    is_new: bool


@dataclass
class SummaryData:
    """Contains generated summary data."""
    student_name: str
    week_start: date
    week_end: date
    summary_text: str
    messages_count: int
    marks_count: int
    week_type: str = "current"
    generated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "student_name": self.student_name,
            "week_type": self.week_type,
            "week_start": self.week_start.isoformat(),
            "week_end": self.week_end.isoformat(),
            "messages_count": self.messages_count,
            "marks_count": self.marks_count,
            "generated_at": self.generated_at.isoformat(),
        }


def get_current_week_range() -> tuple[date, date]:
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    return week_start, week_end


def get_last_week_range() -> tuple[date, date]:
    current_start, _ = get_current_week_range()
    week_start = current_start - timedelta(days=7)
    week_end = week_start + timedelta(days=6)
    return week_start, week_end


def get_next_week_range() -> tuple[date, date]:
    current_start, _ = get_current_week_range()
    week_start = current_start + timedelta(days=7)
    week_end = week_start + timedelta(days=6)
    return week_start, week_end


class SummaryModule:
    """Module for aggregating data and building summary prompts."""

    def __init__(self, storage_path: Path | None, student_name: str) -> None:
        self._storage_path = storage_path
        self._student_name = student_name

    def get_week_messages(
        self, week_start: date | None = None, week_end: date | None = None,
    ) -> list[MessageSummary]:
        if week_start is None or week_end is None:
            week_start, week_end = get_current_week_range()
        messages: list[MessageSummary] = []
        if not self._storage_path or not self._storage_path.exists():
            return messages
        for md_file in self._storage_path.glob("*.md"):
            try:
                message = self._parse_message_file(md_file, week_start, week_end)
                if message:
                    messages.append(message)
            except Exception as err:
                _LOGGER.warning("Failed to parse message file %s: %s", md_file, err)
        messages.sort(key=lambda m: m.date or datetime.min, reverse=True)
        return messages

    def get_recent_messages(self, days_back: int = 30) -> list[MessageSummary]:
        messages: list[MessageSummary] = []
        if not self._storage_path or not self._storage_path.exists():
            return messages
        cutoff_date = date.today() - timedelta(days=days_back)
        for md_file in self._storage_path.glob("*.md"):
            try:
                message = self._parse_message_file_full(md_file, cutoff_date)
                if message:
                    messages.append(message)
            except Exception as err:
                _LOGGER.warning("Failed to parse message file %s: %s", md_file, err)
        messages.sort(key=lambda m: m.date or datetime.min, reverse=True)
        return messages

    def _parse_message_file(
        self, file_path: Path, week_start: date, week_end: date,
    ) -> MessageSummary | None:
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
        if message_date:
            msg_date = message_date.date()
            if msg_date < week_start or msg_date > week_end:
                return None
        text_preview = self._extract_text_content(content)
        return MessageSummary(
            title=title, sender=sender, date=message_date,
            text_preview=text_preview[:300] if text_preview else "",
        )

    def _parse_message_file_full(
        self, file_path: Path, cutoff_date: date,
    ) -> MessageSummary | None:
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
        return MessageSummary(
            title=title, sender=sender, date=message_date,
            text_preview=text_content[:1000] if text_content else "",
        )

    def _extract_metadata(self, content: str, key: str) -> str | None:
        pattern = rf"^{key}:\s*(.+)$"
        match = re.search(pattern, content, re.MULTILINE)
        return match.group(1).strip() if match else None

    def _extract_text_content(self, content: str) -> str:
        parts = content.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
        return content.strip()

    def extract_new_marks(
        self, marks_data: MarksData | None,
        week_start: date | None = None, week_end: date | None = None,
    ) -> list[MarkSummary]:
        if marks_data is None:
            return []
        if week_start is None or week_end is None:
            week_start, week_end = get_current_week_range()
        marks: list[MarkSummary] = []
        for subject in marks_data.subjects:
            for mark in subject.marks:
                if mark.mark_date:
                    mark_date = mark.mark_date.date()
                    if mark_date < week_start or mark_date > week_end:
                        continue
                marks.append(MarkSummary(
                    subject=subject.subject_name, mark=mark.mark_text,
                    caption=mark.caption, date=mark.mark_date, is_new=mark.is_new,
                ))
        marks.sort(key=lambda m: m.date or datetime.min, reverse=True)
        return marks

    def format_timetable(self, timetable: WeekTimetable | None) -> str:
        if timetable is None:
            return "Rozvrh není k dispozici."
        lines = []
        day_names = {
            0: "Pondělí", 1: "Úterý", 2: "Středa", 3: "Čtvrtek",
            4: "Pátek", 5: "Sobota", 6: "Neděle",
        }
        for day in timetable.days:
            day_name = day_names.get(day.date.weekday(), str(day.date))
            if not day.is_school_day:
                lines.append(f"- {day_name}: {day.day_description or 'Volno'}")
            else:
                subjects = ", ".join(day.subject_abbrevs) if day.subject_abbrevs else "Žádné hodiny"
                lines.append(f"- {day_name} ({day.date.strftime('%d.%m.')}): {subjects}")
        return "\n".join(lines)

    def format_messages(self, messages: list[MessageSummary]) -> str:
        """Format messages for prompt template."""
        if not messages:
            return "Žádné zprávy k dispozici."
        return "\n".join(
            f"- [{m.date.strftime('%d.%m.%Y %H:%M') if m.date else '?'}] "
            f"{m.title} (od: {m.sender}):\n  {m.text_preview[:500]}"
            for m in messages[:20]
        )

    def format_marks(self, marks: list[MarkSummary]) -> str:
        """Format marks for prompt template."""
        if not marks:
            return "Žádné známky v tomto období."
        return "\n".join(
            f"- [{m.date.strftime('%d.%m.%Y') if m.date else '?'}] "
            f"{m.subject}: {m.mark} - {m.caption}"
            for m in marks
        )

    def build_prompt_from_template(
        self,
        template: str,
        messages: list[MessageSummary],
        timetable: WeekTimetable | None,
        marks: list[MarkSummary],
        week_start: date,
        week_end: date,
        week_type: str = "current",
        gdrive_report: str = "",
        student_info: str = "",
    ) -> str:
        """Build prompt from a config template using str.format_map()."""
        week_type_labels = {
            "last": "minulý týden",
            "current": "tento týden",
            "next": "příští týden",
        }
        variables = {
            "week_type": week_type_labels.get(week_type, "tento týden"),
            "date_from": week_start.strftime("%d.%m.%Y"),
            "date_to": week_end.strftime("%d.%m.%Y"),
            "messages": self.format_messages(messages),
            "timetable": self.format_timetable(timetable),
            "marks": self.format_marks(marks),
            "gdrive_report": gdrive_report or "Žádný report k dispozici.",
            "student_info": f"\nInformace o studentovi:\n{student_info}\n" if student_info else "",
        }
        try:
            return template.format_map(variables)
        except KeyError as e:
            _LOGGER.warning("Unknown template variable: %s", e)
            return template

    def get_system_instruction(self) -> str:
        return (
            "Jsi asistent pro rodiče, který shrnuje školní aktivity jejich dětí. "
            "Piš stručně, jasně a věcně v češtině. "
            "Zaměř se na důležité informace, které rodiče potřebují vědět."
        )
