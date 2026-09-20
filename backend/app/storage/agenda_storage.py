"""YAML storage for extracted calendar events and checklist tasks.

Three files per student under ``app_data/agenda/<Student>/``:

``events.yaml`` / ``tasks.yaml``
    AI-owned and fully regenerable.  Re-extracting a message replaces exactly
    that message's records and leaves every other source untouched.

``state.yaml``
    User-owned: done and dismissed flags keyed by record id.  Kept separate so
    a re-extraction can never wipe what the user did.

``digest.yaml``
    Bookkeeping for the daily reminder push, so a restart cannot resend it.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from ..modules.agenda import AgendaEvent, AgendaTask, ItemState
from .komens_storage import sanitize_filename

_LOGGER = logging.getLogger("bakalari.agenda_storage")

_EVENTS_FILE = "events.yaml"
_TASKS_FILE = "tasks.yaml"
_STATE_FILE = "state.yaml"
_DIGEST_FILE = "digest.yaml"


def _dump_yaml(path: Path, data: dict[str, Any]) -> None:
    """Write YAML through a temp file so a crash cannot truncate the original."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )
        tmp.replace(path)
    except OSError as err:
        _LOGGER.error("Failed to write %s: %s", path, err)
        tmp.unlink(missing_ok=True)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as err:
        _LOGGER.error("Failed to read %s: %s", path, err)
        return {}
    return data if isinstance(data, dict) else {}


class AgendaStorage:
    """Per-student persistence of agenda records and their user state."""

    def __init__(self, storage_path: str | Path, student_name: str) -> None:
        self._base_path = Path(storage_path)
        self._student_name = sanitize_filename(student_name)
        self._student_path = self._base_path / self._student_name

    @property
    def storage_path(self) -> Path:
        return self._student_path

    def ensure_directory(self) -> None:
        self._student_path.mkdir(parents=True, exist_ok=True)

    # ── AI-owned records ──────────────────────────────────────────────────

    def load_events(self) -> list[AgendaEvent]:
        raw = _load_yaml(self._student_path / _EVENTS_FILE).get("events") or []
        events = []
        for item in raw:
            if isinstance(item, dict):
                event = AgendaEvent.from_dict(item)
                if event:
                    events.append(event)
        return events

    def load_tasks(self) -> list[AgendaTask]:
        raw = _load_yaml(self._student_path / _TASKS_FILE).get("tasks") or []
        tasks = []
        for item in raw:
            if isinstance(item, dict):
                task = AgendaTask.from_dict(item)
                if task:
                    tasks.append(task)
        return tasks

    def save_events(self, events: list[AgendaEvent]) -> None:
        self.ensure_directory()
        _dump_yaml(
            self._student_path / _EVENTS_FILE,
            {"events": [e.to_dict() for e in events]},
        )

    def save_tasks(self, tasks: list[AgendaTask]) -> None:
        self.ensure_directory()
        _dump_yaml(
            self._student_path / _TASKS_FILE,
            {"tasks": [t.to_dict() for t in tasks]},
        )

    def replace_source(
        self,
        source: str,
        events: list[AgendaEvent],
        tasks: list[AgendaTask],
    ) -> None:
        """Swap in the records extracted from one message.

        Records of other sources are left alone, and state entries belonging to
        records this source no longer produces are pruned.
        """
        kept_events = [e for e in self.load_events() if e.source != source]
        kept_tasks = [t for t in self.load_tasks() if t.source != source]
        self.save_events(kept_events + events)
        self.save_tasks(kept_tasks + tasks)

        live_ids = {e.id for e in events} | {t.id for t in tasks}
        state = self.load_state()
        stale = [
            item_id
            for item_id in state
            if item_id.startswith(f"{source}-") and item_id not in live_ids
        ]
        if stale:
            for item_id in stale:
                del state[item_id]
            self.save_state(state)

    def known_sources(self) -> set[str]:
        """Sources that already contributed records (even zero of them)."""
        return {e.source for e in self.load_events()} | {
            t.source for t in self.load_tasks()
        }

    # ── User-owned state ──────────────────────────────────────────────────

    def load_state(self) -> dict[str, ItemState]:
        raw = _load_yaml(self._student_path / _STATE_FILE).get("items") or {}
        if not isinstance(raw, dict):
            return {}
        return {
            str(key): ItemState.from_dict(value)
            for key, value in raw.items()
            if isinstance(value, dict)
        }

    def save_state(self, state: dict[str, ItemState]) -> None:
        self.ensure_directory()
        _dump_yaml(
            self._student_path / _STATE_FILE,
            {"items": {key: value.to_dict() for key, value in state.items()}},
        )

    def set_state(
        self,
        item_id: str,
        done: bool | None = None,
        dismissed: bool | None = None,
    ) -> ItemState:
        """Update one record's user state and return it."""
        state = self.load_state()
        entry = state.get(item_id, ItemState())
        now = datetime.now()

        if done is not None:
            entry.done = done
            entry.done_at = now if done else None
        if dismissed is not None:
            entry.dismissed = dismissed
            entry.dismissed_at = now if dismissed else None

        if entry.is_empty:
            state.pop(item_id, None)
        else:
            state[item_id] = entry
        self.save_state(state)
        return entry

    def get_state(self, item_id: str) -> ItemState:
        return self.load_state().get(item_id, ItemState())

    # ── Reminder bookkeeping ──────────────────────────────────────────────

    def last_digest_date(self) -> date | None:
        raw = _load_yaml(self._student_path / _DIGEST_FILE).get("last_sent")
        if isinstance(raw, date) and not isinstance(raw, datetime):
            return raw
        if isinstance(raw, str):
            try:
                return date.fromisoformat(raw)
            except ValueError:
                return None
        return None

    def set_last_digest_date(self, value: date) -> None:
        self.ensure_directory()
        _dump_yaml(self._student_path / _DIGEST_FILE, {"last_sent": value.isoformat()})

    # ── Stats ─────────────────────────────────────────────────────────────

    def get_statistics(self) -> dict[str, Any]:
        events = self.load_events()
        tasks = self.load_tasks()
        state = self.load_state()
        return {
            "storage_path": str(self._student_path),
            "event_count": len(events),
            "task_count": len(tasks),
            "done_count": sum(1 for s in state.values() if s.done),
            "dismissed_count": sum(1 for s in state.values() if s.dismissed),
        }
