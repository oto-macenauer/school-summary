"""Tests for AgendaStorage: YAML persistence and the user state overlay."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest
import yaml

from app.modules.agenda import ItemState, parse_events, parse_tasks
from app.storage.agenda_storage import AgendaStorage

STUDENT = "Alice Nováková"


@pytest.fixture
def storage(tmp_path: Path) -> AgendaStorage:
    return AgendaStorage(tmp_path / "agenda", STUDENT)


def _events(source: str, *specs):
    return parse_events(list(specs), source, source.split("-")[0], datetime(2026, 9, 20))


def _tasks(source: str, *specs):
    return parse_tasks(list(specs), source, source.split("-")[0], datetime(2026, 9, 20))


class TestPaths:
    def test_student_directory_is_sanitised(self, tmp_path: Path) -> None:
        storage = AgendaStorage(tmp_path, "Bad/Name:?")
        assert "/" not in storage.storage_path.name
        assert ":" not in storage.storage_path.name

    def test_missing_directory_reads_as_empty(self, storage: AgendaStorage) -> None:
        assert storage.load_events() == []
        assert storage.load_tasks() == []
        assert storage.load_state() == {}


class TestRoundTrip:
    def test_events_round_trip(self, storage: AgendaStorage) -> None:
        events = _events(
            "komens-1",
            {"kind": "test", "title": "Písemka", "date": "2026-10-14"},
            {"kind": "trip", "title": "Výlet", "date": "2026-10-20", "date_to": "2026-10-21"},
        )
        storage.save_events(events)
        loaded = storage.load_events()
        assert loaded == events

    def test_tasks_round_trip(self, storage: AgendaStorage) -> None:
        tasks = _tasks(
            "komens-1",
            {"kind": "pay", "title": "Záloha", "due": "2026-10-10", "amount": 3500},
        )
        storage.save_tasks(tasks)
        assert storage.load_tasks() == tasks

    def test_written_yaml_is_human_readable(self, storage: AgendaStorage) -> None:
        storage.save_events(
            _events("komens-1", {"kind": "test", "title": "Písemka", "date": "2026-10-14"})
        )
        raw = (storage.storage_path / "events.yaml").read_text(encoding="utf-8")
        assert "Písemka" in raw  # not escaped into \\uXXXX
        parsed = yaml.safe_load(raw)
        assert parsed["events"][0]["kind"] == "test"

    def test_corrupt_yaml_reads_as_empty(self, storage: AgendaStorage) -> None:
        storage.ensure_directory()
        (storage.storage_path / "events.yaml").write_text("{[not yaml", encoding="utf-8")
        assert storage.load_events() == []

    def test_invalid_records_are_skipped(self, storage: AgendaStorage) -> None:
        storage.ensure_directory()
        (storage.storage_path / "events.yaml").write_text(
            yaml.safe_dump(
                {"events": [{"id": "x", "title": "No date"}, {"id": "y", "title": "Ok", "date_from": "2026-10-14"}]}
            ),
            encoding="utf-8",
        )
        assert [e.id for e in storage.load_events()] == ["y"]


class TestReplaceSource:
    def test_replaces_only_that_source(self, storage: AgendaStorage) -> None:
        storage.replace_source(
            "komens-1",
            _events("komens-1", {"title": "První", "date": "2026-10-14"}),
            _tasks("komens-1", {"title": "Úkol 1"}),
        )
        storage.replace_source(
            "mail-2",
            _events("mail-2", {"title": "Druhá", "date": "2026-10-15"}),
            [],
        )
        # Re-extracting komens-1 must not touch mail-2
        storage.replace_source(
            "komens-1",
            _events("komens-1", {"title": "První opravená", "date": "2026-10-16"}),
            [],
        )

        titles = {e.title for e in storage.load_events()}
        assert titles == {"První opravená", "Druhá"}
        assert storage.load_tasks() == []

    def test_keeps_user_state_of_surviving_records(self, storage: AgendaStorage) -> None:
        spec = {"kind": "pay", "title": "Záloha", "due": "2026-10-10"}
        storage.replace_source("komens-1", [], _tasks("komens-1", spec))
        task_id = storage.load_tasks()[0].id
        storage.set_state(task_id, done=True)

        # The same message is re-processed and yields the same record
        storage.replace_source("komens-1", [], _tasks("komens-1", spec))

        assert storage.get_state(task_id).done is True

    def test_prunes_state_of_vanished_records(self, storage: AgendaStorage) -> None:
        storage.replace_source(
            "komens-1", [], _tasks("komens-1", {"title": "A"}, {"title": "B"}),
        )
        storage.set_state("komens-1-t1", done=True)
        assert "komens-1-t1" in storage.load_state()

        # Re-extraction now produces only one task
        storage.replace_source("komens-1", [], _tasks("komens-1", {"title": "A"}))

        assert "komens-1-t1" not in storage.load_state()

    def test_prune_does_not_touch_other_sources(self, storage: AgendaStorage) -> None:
        storage.replace_source("komens-1", [], _tasks("komens-1", {"title": "A"}))
        storage.replace_source("mail-2", [], _tasks("mail-2", {"title": "B"}))
        storage.set_state("mail-2-t0", done=True)

        storage.replace_source("komens-1", [], [])

        assert storage.get_state("mail-2-t0").done is True

    def test_known_sources(self, storage: AgendaStorage) -> None:
        storage.replace_source(
            "komens-1", _events("komens-1", {"title": "A", "date": "2026-10-14"}), [],
        )
        storage.replace_source("mail-2", [], _tasks("mail-2", {"title": "B"}))
        assert storage.known_sources() == {"komens-1", "mail-2"}


class TestState:
    def test_set_and_get(self, storage: AgendaStorage) -> None:
        state = storage.set_state("komens-1-t0", done=True)
        assert state.done is True
        assert state.done_at is not None
        assert storage.get_state("komens-1-t0").done is True

    def test_partial_update_keeps_other_flag(self, storage: AgendaStorage) -> None:
        storage.set_state("komens-1-t0", done=True)
        storage.set_state("komens-1-t0", dismissed=True)
        state = storage.get_state("komens-1-t0")
        assert state.done is True and state.dismissed is True

    def test_clearing_both_flags_drops_the_entry(self, storage: AgendaStorage) -> None:
        storage.set_state("komens-1-t0", done=True)
        storage.set_state("komens-1-t0", done=False)
        assert "komens-1-t0" not in storage.load_state()

    def test_undone_clears_timestamp(self, storage: AgendaStorage) -> None:
        storage.set_state("komens-1-t0", done=True, dismissed=True)
        storage.set_state("komens-1-t0", done=False)
        assert storage.get_state("komens-1-t0").done_at is None

    def test_state_round_trip(self, storage: AgendaStorage) -> None:
        storage.save_state({"a": ItemState(done=True, done_at=datetime(2026, 9, 20, 8, 0))})
        loaded = storage.load_state()
        assert loaded["a"].done_at == datetime(2026, 9, 20, 8, 0)

    def test_unknown_id_is_default(self, storage: AgendaStorage) -> None:
        assert storage.get_state("nope").is_empty


class TestDigestBookkeeping:
    def test_unset_is_none(self, storage: AgendaStorage) -> None:
        assert storage.last_digest_date() is None

    def test_round_trip(self, storage: AgendaStorage) -> None:
        storage.set_last_digest_date(date(2026, 9, 20))
        assert storage.last_digest_date() == date(2026, 9, 20)

    def test_invalid_value_is_none(self, storage: AgendaStorage) -> None:
        storage.ensure_directory()
        (storage.storage_path / "digest.yaml").write_text(
            "last_sent: not-a-date", encoding="utf-8",
        )
        assert storage.last_digest_date() is None


class TestStatistics:
    def test_counts(self, storage: AgendaStorage) -> None:
        storage.replace_source(
            "komens-1",
            _events("komens-1", {"title": "A", "date": "2026-10-14"}),
            _tasks("komens-1", {"title": "B"}, {"title": "C"}),
        )
        storage.set_state("komens-1-t0", done=True)
        storage.set_state("komens-1-e0", dismissed=True)

        stats = storage.get_statistics()
        assert stats["event_count"] == 1
        assert stats["task_count"] == 2
        assert stats["done_count"] == 1
        assert stats["dismissed_count"] == 1
