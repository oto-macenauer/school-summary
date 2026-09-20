"""Calendar events and checklist tasks extracted from messages.

Komens messages, school mail and weekly reports carry two kinds of actionable
information: things that happen on a date (tests, trips, meetings) and things
somebody has to do (pay a deposit, bring a swimsuit, sign a form).  The AI
tagging pass extracts both; this module holds their models and the parsing
that turns raw AI output into validated records.

Records are owned by the message they came from: re-extracting a message
replaces its records.  Anything the user changes (done, dismissed) lives in a
separate state overlay so it survives re-extraction — see
``storage.agenda_storage``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

_LOGGER = logging.getLogger("bakalari.agenda")

# Calendar entry kinds. Unknown kinds from the AI collapse to "event".
EVENT_KINDS: tuple[str, ...] = (
    "test",
    "exam",
    "homework",
    "trip",
    "event",
    "meeting",
    "holiday",
    "deadline",
)
DEFAULT_EVENT_KIND = "event"

# Checklist entry kinds. Unknown kinds collapse to "other".
TASK_KINDS: tuple[str, ...] = (
    "pay",
    "bring",
    "prepare",
    "buy",
    "sign",
    "return",
    "other",
)
DEFAULT_TASK_KIND = "other"

# Titles longer than this are truncated — the AI occasionally returns a whole
# paragraph, which breaks the agenda layout and helps nobody.
MAX_TITLE_LENGTH = 200
MAX_NOTE_LENGTH = 500


def _clean_text(value: Any, max_length: int) -> str:
    """Normalise an AI-supplied string: collapse whitespace, cap the length."""
    if not isinstance(value, str):
        return ""
    text = " ".join(value.split())
    if len(text) > max_length:
        text = text[: max_length - 1].rstrip() + "…"
    return text


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def _parse_time(value: Any) -> str | None:
    """Accept ``HH:MM`` (or ``H:MM``) and normalise to zero-padded ``HH:MM``."""
    if not isinstance(value, str) or ":" not in value:
        return None
    head = value.strip().split()[0]
    parts = head.split(":")
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except (ValueError, IndexError):
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return f"{hour:02d}:{minute:02d}"


def _parse_amount(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        amount = float(value)
    elif isinstance(value, str):
        # "3 500 Kč" / "3500,-" / "1 234,50"
        cleaned = (
            value.replace(" ", "")
            .replace(" ", "")
            .replace(",", ".")
            .rstrip("-")
        )
        digits = "".join(c for c in cleaned if c.isdigit() or c == ".")
        if not digits or digits.count(".") > 1:
            return None
        try:
            amount = float(digits)
        except ValueError:
            return None
    else:
        return None
    if amount <= 0:
        return None
    return round(amount, 2)


def _normalise_kind(value: Any, allowed: tuple[str, ...], fallback: str) -> str:
    if isinstance(value, str):
        kind = value.strip().lower()
        if kind in allowed:
            return kind
    return fallback


@dataclass
class AgendaEvent:
    """Something that happens on a date — the calendar view's unit."""

    id: str
    source: str
    source_category: str
    kind: str
    title: str
    date_from: date
    date_to: date | None = None
    time_from: str | None = None
    subject: str | None = None
    location: str | None = None
    note: str | None = None
    extracted_at: datetime | None = None

    @property
    def date_end(self) -> date:
        """Last day the event covers (same as ``date_from`` for single days)."""
        return self.date_to or self.date_from

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "source_category": self.source_category,
            "kind": self.kind,
            "title": self.title,
            "date_from": self.date_from.isoformat(),
            "date_to": self.date_to.isoformat() if self.date_to else None,
            "time_from": self.time_from,
            "subject": self.subject,
            "location": self.location,
            "note": self.note,
            "extracted_at": self.extracted_at.isoformat() if self.extracted_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgendaEvent | None:
        date_from = _parse_date(data.get("date_from"))
        if not date_from or not data.get("id"):
            return None
        extracted_at = None
        raw_extracted = data.get("extracted_at")
        if raw_extracted:
            try:
                extracted_at = datetime.fromisoformat(str(raw_extracted))
            except ValueError:
                extracted_at = None
        return cls(
            id=str(data["id"]),
            source=str(data.get("source", "")),
            source_category=str(data.get("source_category", "")),
            kind=_normalise_kind(data.get("kind"), EVENT_KINDS, DEFAULT_EVENT_KIND),
            title=str(data.get("title", "")),
            date_from=date_from,
            date_to=_parse_date(data.get("date_to")),
            time_from=_parse_time(data.get("time_from")),
            subject=data.get("subject") or None,
            location=data.get("location") or None,
            note=data.get("note") or None,
            extracted_at=extracted_at,
        )


@dataclass
class AgendaTask:
    """Something somebody has to do — the checklist view's unit."""

    id: str
    source: str
    source_category: str
    kind: str
    title: str
    due: date | None = None
    amount: float | None = None
    currency: str | None = None
    subject: str | None = None
    note: str | None = None
    extracted_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "source_category": self.source_category,
            "kind": self.kind,
            "title": self.title,
            "due": self.due.isoformat() if self.due else None,
            "amount": self.amount,
            "currency": self.currency,
            "subject": self.subject,
            "note": self.note,
            "extracted_at": self.extracted_at.isoformat() if self.extracted_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgendaTask | None:
        if not data.get("id") or not data.get("title"):
            return None
        extracted_at = None
        raw_extracted = data.get("extracted_at")
        if raw_extracted:
            try:
                extracted_at = datetime.fromisoformat(str(raw_extracted))
            except ValueError:
                extracted_at = None
        return cls(
            id=str(data["id"]),
            source=str(data.get("source", "")),
            source_category=str(data.get("source_category", "")),
            kind=_normalise_kind(data.get("kind"), TASK_KINDS, DEFAULT_TASK_KIND),
            title=str(data["title"]),
            due=_parse_date(data.get("due")),
            amount=_parse_amount(data.get("amount")),
            currency=data.get("currency") or None,
            subject=data.get("subject") or None,
            note=data.get("note") or None,
            extracted_at=extracted_at,
        )


@dataclass
class ItemState:
    """User-owned state for one agenda record, kept out of the AI-owned files."""

    done: bool = False
    done_at: datetime | None = None
    dismissed: bool = False
    dismissed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "done": self.done,
            "done_at": self.done_at.isoformat() if self.done_at else None,
            "dismissed": self.dismissed,
            "dismissed_at": self.dismissed_at.isoformat() if self.dismissed_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ItemState:
        def _dt(key: str) -> datetime | None:
            raw = data.get(key)
            if not raw:
                return None
            try:
                return datetime.fromisoformat(str(raw))
            except ValueError:
                return None

        return cls(
            done=bool(data.get("done", False)),
            done_at=_dt("done_at"),
            dismissed=bool(data.get("dismissed", False)),
            dismissed_at=_dt("dismissed_at"),
        )

    @property
    def is_empty(self) -> bool:
        return not self.done and not self.dismissed


@dataclass
class MessageAgenda:
    """Everything the AI extracted from one message."""

    events: list[AgendaEvent] = field(default_factory=list)
    tasks: list[AgendaTask] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.events and not self.tasks


def parse_events(
    raw_items: Any,
    source: str,
    source_category: str,
    extracted_at: datetime | None = None,
) -> list[AgendaEvent]:
    """Build validated events from the AI's ``events`` array for one message."""
    if not isinstance(raw_items, list):
        return []

    events: list[AgendaEvent] = []
    for index, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            continue
        title = _clean_text(raw.get("title"), MAX_TITLE_LENGTH)
        date_from = _parse_date(raw.get("date") or raw.get("date_from"))
        if not title or not date_from:
            # An event without a title or a date cannot be placed on a calendar.
            continue
        date_to = _parse_date(raw.get("date_to"))
        if date_to and date_to < date_from:
            date_to = None
        events.append(
            AgendaEvent(
                id=f"{source}-e{index}",
                source=source,
                source_category=source_category,
                kind=_normalise_kind(raw.get("kind"), EVENT_KINDS, DEFAULT_EVENT_KIND),
                title=title,
                date_from=date_from,
                date_to=date_to,
                time_from=_parse_time(raw.get("time_from") or raw.get("time")),
                subject=_clean_text(raw.get("subject"), 80) or None,
                location=_clean_text(raw.get("location"), 120) or None,
                note=_clean_text(raw.get("note"), MAX_NOTE_LENGTH) or None,
                extracted_at=extracted_at,
            )
        )
    return events


def parse_tasks(
    raw_items: Any,
    source: str,
    source_category: str,
    extracted_at: datetime | None = None,
) -> list[AgendaTask]:
    """Build validated tasks from the AI's ``tasks`` array for one message."""
    if not isinstance(raw_items, list):
        return []

    tasks: list[AgendaTask] = []
    for index, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            continue
        title = _clean_text(raw.get("title"), MAX_TITLE_LENGTH)
        if not title:
            continue
        amount = _parse_amount(raw.get("amount"))
        currency = _clean_text(raw.get("currency"), 8).upper() or None
        if amount and not currency:
            currency = "CZK"
        tasks.append(
            AgendaTask(
                id=f"{source}-t{index}",
                source=source,
                source_category=source_category,
                kind=_normalise_kind(raw.get("kind"), TASK_KINDS, DEFAULT_TASK_KIND),
                title=title,
                due=_parse_date(raw.get("due") or raw.get("date")),
                amount=amount,
                currency=currency,
                subject=_clean_text(raw.get("subject"), 80) or None,
                note=_clean_text(raw.get("note"), MAX_NOTE_LENGTH) or None,
                extracted_at=extracted_at,
            )
        )
    return tasks


def plural_cs(count: int, one: str, few: str, many: str) -> str:
    """Czech agreement after a number: 1, 2–4, and 5+ (or 0) take three forms."""
    n = abs(int(count))
    if n == 1:
        return one
    if 2 <= n <= 4:
        return few
    return many


def sort_events(events: list[AgendaEvent]) -> list[AgendaEvent]:
    """Chronological, all-day entries before timed ones on the same day."""
    return sorted(events, key=lambda e: (e.date_from, e.time_from or "", e.title))


def sort_tasks(tasks: list[AgendaTask]) -> list[AgendaTask]:
    """Due first (soonest first), undated last."""
    return sorted(
        tasks,
        key=lambda t: (t.due is None, t.due or date.max, t.title),
    )


def filter_events_window(
    events: list[AgendaEvent],
    today: date,
    past_days: int,
    future_days: int,
) -> list[AgendaEvent]:
    """Keep events overlapping ``[today - past_days, today + future_days]``.

    A multi-day trip counts as upcoming until its last day has passed.
    """
    start = today - timedelta(days=max(past_days, 0))
    end = today + timedelta(days=max(future_days, 0))
    return [e for e in events if e.date_end >= start and e.date_from <= end]


def upcoming_events(
    events: list[AgendaEvent], today: date, days: int,
) -> list[AgendaEvent]:
    """Events happening today or within the next ``days`` days."""
    end = today + timedelta(days=max(days, 0))
    return sort_events(
        [e for e in events if e.date_end >= today and e.date_from <= end]
    )
