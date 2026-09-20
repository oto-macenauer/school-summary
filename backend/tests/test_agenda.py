"""Tests for the agenda module: event/task parsing, sorting and windowing."""

from __future__ import annotations

from datetime import date, datetime

from app.modules.agenda import (
    AgendaEvent,
    AgendaTask,
    ItemState,
    MessageAgenda,
    filter_events_window,
    parse_events,
    parse_tasks,
    plural_cs,
    sort_events,
    sort_tasks,
    upcoming_events,
)

SOURCE = "komens-1234"
NOW = datetime(2026, 9, 20, 10, 0, 0)


class TestParseEvents:
    """AI output → validated calendar entries."""

    def test_minimal_event(self) -> None:
        events = parse_events(
            [{"kind": "test", "title": "Písemka", "date": "2026-10-14"}],
            SOURCE, "komens", NOW,
        )
        assert len(events) == 1
        event = events[0]
        assert event.id == "komens-1234-e0"
        assert event.source == SOURCE
        assert event.source_category == "komens"
        assert event.kind == "test"
        assert event.date_from == date(2026, 10, 14)
        assert event.date_to is None
        assert event.extracted_at == NOW

    def test_full_event(self) -> None:
        events = parse_events(
            [
                {
                    "kind": "trip",
                    "title": "Lyžařský kurz",
                    "date": "2026-01-12",
                    "date_to": "2026-01-16",
                    "time_from": "7:30",
                    "subject": "Tělesná výchova",
                    "location": "Krkonoše",
                    "note": "Sraz u školy",
                }
            ],
            SOURCE, "komens", NOW,
        )
        event = events[0]
        assert event.kind == "trip"
        assert event.date_to == date(2026, 1, 16)
        assert event.time_from == "07:30"  # normalised to zero-padded
        assert event.location == "Krkonoše"
        assert event.date_end == date(2026, 1, 16)

    def test_event_without_date_is_dropped(self) -> None:
        """A calendar entry with no date cannot be placed anywhere."""
        assert parse_events(
            [{"kind": "test", "title": "Někdy bude test"}], SOURCE, "komens",
        ) == []

    def test_event_without_title_is_dropped(self) -> None:
        assert parse_events(
            [{"kind": "test", "date": "2026-10-14"}], SOURCE, "komens",
        ) == []

    def test_unknown_kind_falls_back_to_event(self) -> None:
        events = parse_events(
            [{"kind": "vánoční besídka", "title": "Besídka", "date": "2026-12-20"}],
            SOURCE, "komens",
        )
        assert events[0].kind == "event"

    def test_invalid_date_is_dropped(self) -> None:
        assert parse_events(
            [{"title": "X", "date": "příští týden"}], SOURCE, "komens",
        ) == []

    def test_date_to_before_date_from_is_ignored(self) -> None:
        events = parse_events(
            [{"title": "X", "date": "2026-10-14", "date_to": "2026-10-01"}],
            SOURCE, "komens",
        )
        assert events[0].date_to is None

    def test_invalid_time_is_ignored(self) -> None:
        events = parse_events(
            [{"title": "X", "date": "2026-10-14", "time_from": "ráno"}],
            SOURCE, "komens",
        )
        assert events[0].time_from is None

    def test_out_of_range_time_is_ignored(self) -> None:
        events = parse_events(
            [{"title": "X", "date": "2026-10-14", "time_from": "25:00"}],
            SOURCE, "komens",
        )
        assert events[0].time_from is None

    def test_long_title_is_truncated(self) -> None:
        events = parse_events(
            [{"title": "A" * 500, "date": "2026-10-14"}], SOURCE, "komens",
        )
        assert len(events[0].title) == 200
        assert events[0].title.endswith("…")

    def test_whitespace_is_collapsed(self) -> None:
        events = parse_events(
            [{"title": "Písemka\n  z   matematiky ", "date": "2026-10-14"}],
            SOURCE, "komens",
        )
        assert events[0].title == "Písemka z matematiky"

    def test_ids_are_unique_per_message(self) -> None:
        events = parse_events(
            [
                {"title": "A", "date": "2026-10-14"},
                {"title": "B", "date": "2026-10-15"},
            ],
            SOURCE, "komens",
        )
        assert [e.id for e in events] == ["komens-1234-e0", "komens-1234-e1"]

    def test_non_list_input(self) -> None:
        assert parse_events(None, SOURCE, "komens") == []
        assert parse_events("nope", SOURCE, "komens") == []

    def test_non_dict_entries_are_skipped(self) -> None:
        events = parse_events(
            ["junk", {"title": "A", "date": "2026-10-14"}], SOURCE, "komens",
        )
        assert len(events) == 1


class TestParseTasks:
    """AI output → validated checklist entries."""

    def test_payment_task(self) -> None:
        tasks = parse_tasks(
            [
                {
                    "kind": "pay",
                    "title": "Záloha na lyžák",
                    "due": "2026-10-10",
                    "amount": 3500,
                    "currency": "czk",
                }
            ],
            SOURCE, "komens", NOW,
        )
        task = tasks[0]
        assert task.id == "komens-1234-t0"
        assert task.kind == "pay"
        assert task.due == date(2026, 10, 10)
        assert task.amount == 3500.0
        assert task.currency == "CZK"

    def test_amount_from_formatted_string(self) -> None:
        tasks = parse_tasks(
            [{"kind": "pay", "title": "Platba", "amount": "3 500 Kč"}],
            SOURCE, "komens",
        )
        assert tasks[0].amount == 3500.0
        assert tasks[0].currency == "CZK"  # defaulted once an amount is known

    def test_decimal_amount_with_comma(self) -> None:
        tasks = parse_tasks(
            [{"kind": "pay", "title": "Platba", "amount": "1 234,50"}],
            SOURCE, "komens",
        )
        assert tasks[0].amount == 1234.5

    def test_invalid_amount_is_dropped(self) -> None:
        tasks = parse_tasks(
            [{"kind": "pay", "title": "Platba", "amount": "nevíme"}],
            SOURCE, "komens",
        )
        assert tasks[0].amount is None
        assert tasks[0].currency is None

    def test_zero_amount_is_dropped(self) -> None:
        tasks = parse_tasks(
            [{"kind": "pay", "title": "Platba", "amount": 0}], SOURCE, "komens",
        )
        assert tasks[0].amount is None

    def test_task_without_due_is_kept(self) -> None:
        """Unlike events, a task without a date is still actionable."""
        tasks = parse_tasks(
            [{"kind": "bring", "title": "Přinést cvičky"}], SOURCE, "komens",
        )
        assert len(tasks) == 1
        assert tasks[0].due is None

    def test_task_without_title_is_dropped(self) -> None:
        assert parse_tasks([{"kind": "pay", "due": "2026-10-10"}], SOURCE, "komens") == []

    def test_unknown_kind_falls_back_to_other(self) -> None:
        tasks = parse_tasks(
            [{"kind": "zaplatit", "title": "Platba"}], SOURCE, "komens",
        )
        assert tasks[0].kind == "other"

    def test_date_key_accepted_as_due(self) -> None:
        tasks = parse_tasks(
            [{"kind": "bring", "title": "Plavky", "date": "2026-10-10"}],
            SOURCE, "komens",
        )
        assert tasks[0].due == date(2026, 10, 10)


class TestSerialisation:
    """YAML round trips through to_dict / from_dict."""

    def test_event_round_trip(self) -> None:
        original = parse_events(
            [
                {
                    "kind": "trip",
                    "title": "Exkurze",
                    "date": "2026-10-14",
                    "date_to": "2026-10-15",
                    "time_from": "08:00",
                    "subject": "Dějepis",
                    "location": "Praha",
                    "note": "Vstupné 100 Kč",
                }
            ],
            SOURCE, "komens", NOW,
        )[0]
        restored = AgendaEvent.from_dict(original.to_dict())
        assert restored is not None
        assert restored == original

    def test_task_round_trip(self) -> None:
        original = parse_tasks(
            [
                {
                    "kind": "pay",
                    "title": "Záloha",
                    "due": "2026-10-10",
                    "amount": 3500,
                    "currency": "CZK",
                    "note": "na účet školy",
                }
            ],
            SOURCE, "komens", NOW,
        )[0]
        restored = AgendaTask.from_dict(original.to_dict())
        assert restored is not None
        assert restored == original

    def test_event_from_dict_requires_date_and_id(self) -> None:
        assert AgendaEvent.from_dict({"id": "x", "title": "A"}) is None
        assert AgendaEvent.from_dict({"title": "A", "date_from": "2026-10-14"}) is None

    def test_task_from_dict_requires_id_and_title(self) -> None:
        assert AgendaTask.from_dict({"id": "x"}) is None
        assert AgendaTask.from_dict({"title": "A"}) is None

    def test_event_from_dict_accepts_native_dates(self) -> None:
        """PyYAML parses bare ISO dates into date objects."""
        event = AgendaEvent.from_dict(
            {"id": "x", "title": "A", "date_from": date(2026, 10, 14)}
        )
        assert event is not None
        assert event.date_from == date(2026, 10, 14)

    def test_event_from_dict_bad_extracted_at(self) -> None:
        event = AgendaEvent.from_dict(
            {"id": "x", "title": "A", "date_from": "2026-10-14", "extracted_at": "nope"}
        )
        assert event is not None
        assert event.extracted_at is None


class TestItemState:
    """User-owned done/dismissed state."""

    def test_defaults_are_empty(self) -> None:
        state = ItemState()
        assert state.is_empty
        assert not state.done and not state.dismissed

    def test_round_trip(self) -> None:
        state = ItemState(done=True, done_at=NOW, dismissed=False)
        restored = ItemState.from_dict(state.to_dict())
        assert restored.done is True
        assert restored.done_at == NOW
        assert restored.dismissed is False
        assert not restored.is_empty

    def test_from_dict_ignores_bad_timestamps(self) -> None:
        state = ItemState.from_dict({"done": True, "done_at": "not-a-time"})
        assert state.done is True
        assert state.done_at is None


class TestSortingAndWindows:
    """Ordering and the rolling calendar window."""

    def _event(self, day: int, title: str = "X", time_from: str | None = None):
        return parse_events(
            [{"title": title, "date": f"2026-10-{day:02d}", "time_from": time_from}],
            SOURCE, "komens",
        )[0]

    def test_sort_events_chronologically(self) -> None:
        events = [self._event(20), self._event(14), self._event(17)]
        assert [e.date_from.day for e in sort_events(events)] == [14, 17, 20]

    def test_all_day_before_timed_on_same_day(self) -> None:
        timed = self._event(14, "Timed", "08:00")
        all_day = self._event(14, "All day")
        assert sort_events([timed, all_day])[0] is all_day

    def test_sort_tasks_due_first_undated_last(self) -> None:
        tasks = parse_tasks(
            [
                {"title": "Bez termínu"},
                {"title": "Pozdě", "due": "2026-10-20"},
                {"title": "Brzy", "due": "2026-10-10"},
            ],
            SOURCE, "komens",
        )
        assert [t.title for t in sort_tasks(tasks)] == ["Brzy", "Pozdě", "Bez termínu"]

    def test_window_keeps_recent_past_and_near_future(self) -> None:
        today = date(2026, 10, 15)
        events = [
            self._event(1),   # 14 days back
            self._event(14),  # yesterday
            self._event(20),  # next week
        ]
        kept = filter_events_window(events, today, past_days=7, future_days=30)
        assert [e.date_from.day for e in sort_events(kept)] == [14, 20]

    def test_window_keeps_multi_day_event_still_running(self) -> None:
        """A trip that started before the window still counts as upcoming."""
        today = date(2026, 10, 15)
        trip = parse_events(
            [{"title": "Lyžák", "date": "2026-10-01", "date_to": "2026-10-16"}],
            SOURCE, "komens",
        )[0]
        assert filter_events_window([trip], today, past_days=3, future_days=30) == [trip]

    def test_upcoming_events_excludes_the_past(self) -> None:
        today = date(2026, 10, 15)
        events = [self._event(10), self._event(16), self._event(30)]
        upcoming = upcoming_events(events, today, days=10)
        assert [e.date_from.day for e in upcoming] == [16]

    def test_upcoming_includes_today(self) -> None:
        today = date(2026, 10, 15)
        assert upcoming_events([self._event(15)], today, days=0)


class TestCzechPlural:
    """Counts shown to the user have to agree with the noun."""

    def test_forms(self) -> None:
        assert plural_cs(1, "další", "další", "dalších") == "další"
        assert plural_cs(3, "den", "dny", "dní") == "dny"
        assert plural_cs(7, "den", "dny", "dní") == "dní"
        assert plural_cs(0, "den", "dny", "dní") == "dní"


class TestMessageAgenda:
    def test_is_empty(self) -> None:
        assert MessageAgenda().is_empty
        event = parse_events(
            [{"title": "A", "date": "2026-10-14"}], SOURCE, "komens",
        )
        assert not MessageAgenda(events=event).is_empty
