"""Tests for the calendar and checklist HTTP endpoints."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from app import dependencies
from app.main import app
from app.models.config import AgendaConfig, AppConfig
from app.modules.agenda import parse_events, parse_tasks
from app.storage.agenda_storage import AgendaStorage

STUDENT = "Alice"
TODAY = date.today()


def _day(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


@pytest.fixture
def storage(tmp_path: Path) -> AgendaStorage:
    store = AgendaStorage(tmp_path / "agenda", STUDENT)
    store.replace_source(
        "komens-1",
        parse_events(
            [
                {"kind": "test", "title": "Písemka", "date": _day(3)},
                {"kind": "trip", "title": "Výlet", "date": _day(-20)},
            ],
            "komens-1", "komens", datetime.now(),
        ),
        parse_tasks(
            [
                {"kind": "pay", "title": "Záloha", "due": _day(-2), "amount": 3500},
                {"kind": "bring", "title": "Cvičky", "due": _day(3)},
                {"kind": "buy", "title": "Barvy", "due": _day(40)},
                {"kind": "other", "title": "Bez termínu"},
            ],
            "komens-1", "komens", datetime.now(),
        ),
    )
    return store


@pytest.fixture
def client(storage: AgendaStorage) -> Iterator[TestClient]:
    ctx = SimpleNamespace(name=STUDENT, agenda_storage=storage)
    config = AppConfig(agenda=AgendaConfig(past_window_days=14, future_window_days=30))
    manager = SimpleNamespace(
        config=config,
        get_student=lambda name: ctx if name.lower() == STUDENT.lower() else None,
    )
    dependencies.set_student_manager(manager)
    # No context manager: the app lifespan would log in to the real Bakalari.
    yield TestClient(app)
    dependencies.set_student_manager(None)


class TestEventsEndpoint:
    def test_returns_events_in_the_window(self, client: TestClient) -> None:
        data = client.get(f"/api/students/{STUDENT}/agenda/events").json()
        titles = [e["title"] for e in data["events"]]
        # The 20-day-old trip falls outside the 14-day past window
        assert titles == ["Písemka"]
        assert data["today"] == TODAY.isoformat()
        assert data["total"] == 2

    def test_all_time_ignores_the_window(self, client: TestClient) -> None:
        data = client.get(
            f"/api/students/{STUDENT}/agenda/events", params={"all_time": True},
        ).json()
        assert {e["title"] for e in data["events"]} == {"Písemka", "Výlet"}

    def test_explicit_window_overrides_config(self, client: TestClient) -> None:
        data = client.get(
            f"/api/students/{STUDENT}/agenda/events", params={"past_days": 30},
        ).json()
        assert len(data["events"]) == 2
        assert data["window"]["past_days"] == 30

    def test_events_are_sorted_chronologically(self, client: TestClient) -> None:
        data = client.get(
            f"/api/students/{STUDENT}/agenda/events", params={"all_time": True},
        ).json()
        dates = [e["date_from"] for e in data["events"]]
        assert dates == sorted(dates)

    def test_dismissed_hidden_by_default(
        self, client: TestClient, storage: AgendaStorage,
    ) -> None:
        storage.set_state("komens-1-e0", dismissed=True)
        data = client.get(f"/api/students/{STUDENT}/agenda/events").json()
        assert data["events"] == []

    def test_dismissed_can_be_included(
        self, client: TestClient, storage: AgendaStorage,
    ) -> None:
        storage.set_state("komens-1-e0", dismissed=True)
        data = client.get(
            f"/api/students/{STUDENT}/agenda/events",
            params={"include_dismissed": True},
        ).json()
        assert data["events"][0]["dismissed"] is True

    def test_unknown_student_is_404(self, client: TestClient) -> None:
        assert client.get("/api/students/Nikdo/agenda/events").status_code == 404


class TestTasksEndpoint:
    def test_returns_all_tasks_sorted_by_due(self, client: TestClient) -> None:
        data = client.get(f"/api/students/{STUDENT}/agenda/tasks").json()
        titles = [t["title"] for t in data["tasks"]]
        assert titles == ["Záloha", "Cvičky", "Barvy", "Bez termínu"]

    def test_counts(self, client: TestClient) -> None:
        counts = client.get(f"/api/students/{STUDENT}/agenda/tasks").json()["counts"]
        assert counts == {"open": 4, "overdue": 1, "due_soon": 1}

    def test_done_tasks_can_be_excluded(
        self, client: TestClient, storage: AgendaStorage,
    ) -> None:
        storage.set_state("komens-1-t0", done=True)
        data = client.get(
            f"/api/students/{STUDENT}/agenda/tasks", params={"include_done": False},
        ).json()
        assert "Záloha" not in [t["title"] for t in data["tasks"]]
        assert data["counts"]["open"] == 3
        assert data["counts"]["overdue"] == 0

    def test_done_state_is_exposed(
        self, client: TestClient, storage: AgendaStorage,
    ) -> None:
        storage.set_state("komens-1-t0", done=True)
        data = client.get(f"/api/students/{STUDENT}/agenda/tasks").json()
        task = next(t for t in data["tasks"] if t["title"] == "Záloha")
        assert task["done"] is True
        assert task["done_at"] is not None

    def test_amount_survives_the_round_trip(self, client: TestClient) -> None:
        data = client.get(f"/api/students/{STUDENT}/agenda/tasks").json()
        task = next(t for t in data["tasks"] if t["title"] == "Záloha")
        assert task["amount"] == 3500
        assert task["currency"] == "CZK"


class TestItemStateEndpoint:
    def test_mark_done(self, client: TestClient, storage: AgendaStorage) -> None:
        response = client.post(
            f"/api/students/{STUDENT}/agenda/items/komens-1-t0/state",
            json={"done": True},
        )
        assert response.status_code == 200
        assert response.json()["done"] is True
        assert storage.get_state("komens-1-t0").done is True

    def test_dismiss_event(self, client: TestClient, storage: AgendaStorage) -> None:
        response = client.post(
            f"/api/students/{STUDENT}/agenda/items/komens-1-e0/state",
            json={"dismissed": True},
        )
        assert response.status_code == 200
        assert storage.get_state("komens-1-e0").dismissed is True

    def test_undo(self, client: TestClient, storage: AgendaStorage) -> None:
        client.post(
            f"/api/students/{STUDENT}/agenda/items/komens-1-t0/state",
            json={"done": True},
        )
        client.post(
            f"/api/students/{STUDENT}/agenda/items/komens-1-t0/state",
            json={"done": False},
        )
        assert storage.get_state("komens-1-t0").done is False

    def test_empty_request_is_400(self, client: TestClient) -> None:
        response = client.post(
            f"/api/students/{STUDENT}/agenda/items/komens-1-t0/state", json={},
        )
        assert response.status_code == 400

    def test_unknown_item_is_404(self, client: TestClient) -> None:
        response = client.post(
            f"/api/students/{STUDENT}/agenda/items/komens-9-t9/state",
            json={"done": True},
        )
        assert response.status_code == 404
