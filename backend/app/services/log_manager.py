"""Categorized in-memory log ring buffer."""

from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class LogCategory(str, Enum):
    AUTH = "auth"
    TIMETABLE = "timetable"
    MARKS = "marks"
    KOMENS = "komens"
    SUMMARY = "summary"
    PREPARE = "prepare"
    GDRIVE = "gdrive"
    GEMINI = "gemini"
    SCHEDULER = "scheduler"
    CONFIG = "config"
    SYSTEM = "system"


# Map logger names to categories
_LOGGER_CATEGORY_MAP: dict[str, LogCategory] = {
    "bakalari.auth": LogCategory.AUTH,
    "bakalari.client": LogCategory.AUTH,
    "bakalari.timetable": LogCategory.TIMETABLE,
    "bakalari.marks": LogCategory.MARKS,
    "bakalari.komens": LogCategory.KOMENS,
    "bakalari.komens_storage": LogCategory.KOMENS,
    "bakalari.summary": LogCategory.SUMMARY,
    "bakalari.prepare": LogCategory.PREPARE,
    "bakalari.gdrive": LogCategory.GDRIVE,
    "bakalari.gdrive_storage": LogCategory.GDRIVE,
    "bakalari.gemini": LogCategory.GEMINI,
    "bakalari.scheduler": LogCategory.SCHEDULER,
    "bakalari.config": LogCategory.CONFIG,
}

MAX_ENTRIES = 2000


@dataclass
class LogEntry:
    timestamp: datetime
    category: LogCategory
    level: str
    message: str
    student: str | None = None
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "category": self.category.value,
            "level": self.level,
            "message": self.message,
            "student": self.student,
            "details": self.details,
        }


class LogManager(logging.Handler):
    """Thread-safe ring buffer log handler that captures application logs."""

    def __init__(self) -> None:
        super().__init__()
        self._entries: deque[LogEntry] = deque(maxlen=MAX_ENTRIES)
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        """Handle a log record from stdlib logging."""
        category = _LOGGER_CATEGORY_MAP.get(record.name, LogCategory.SYSTEM)
        entry = LogEntry(
            timestamp=datetime.fromtimestamp(record.created),
            category=category,
            level=record.levelname,
            message=record.getMessage(),
            student=getattr(record, "student", None),
        )
        with self._lock:
            self._entries.append(entry)

    def log(
        self,
        category: LogCategory,
        level: str,
        message: str,
        student: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Directly add a log entry."""
        entry = LogEntry(
            timestamp=datetime.now(),
            category=category,
            level=level,
            message=message,
            student=student,
            details=details,
        )
        with self._lock:
            self._entries.append(entry)

    def get_logs(
        self,
        category: LogCategory | None = None,
        level: str | None = None,
        student: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LogEntry]:
        """Get filtered log entries, newest first."""
        with self._lock:
            entries = list(self._entries)

        # Filter
        if category is not None:
            entries = [e for e in entries if e.category == category]
        if level is not None:
            entries = [e for e in entries if e.level == level]
        if student is not None:
            entries = [e for e in entries if e.student == student]

        # Newest first
        entries.reverse()

        # Paginate
        return entries[offset : offset + limit]

    def get_categories(self) -> list[LogCategory]:
        return list(LogCategory)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    @property
    def count(self) -> int:
        return len(self._entries)


# Global singleton
_log_manager: LogManager | None = None


def get_log_manager() -> LogManager:
    """Get the global LogManager instance."""
    global _log_manager
    if _log_manager is None:
        _log_manager = LogManager()
    return _log_manager


def setup_logging() -> LogManager:
    """Set up logging with the LogManager handler."""
    manager = get_log_manager()

    # Attach to the bakalari logger hierarchy
    root_logger = logging.getLogger("bakalari")
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(manager)

    # Also add a stdout handler for container logs
    stdout_handler = logging.StreamHandler()
    stdout_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    )
    root_logger.addHandler(stdout_handler)

    return manager
