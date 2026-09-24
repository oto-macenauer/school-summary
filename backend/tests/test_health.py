"""Tests for the liveness and readiness probes."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from app import dependencies
from app.main import app


def _ctx(authenticated: bool) -> SimpleNamespace:
    return SimpleNamespace(
        client=SimpleNamespace(auth=SimpleNamespace(is_authenticated=authenticated)),
    )


@pytest.fixture
def client() -> Iterator[TestClient]:
    dependencies.set_student_manager(None)
    # No context manager: the app lifespan would log in to the real Bakalari.
    yield TestClient(app)
    dependencies.set_student_manager(None)


def _use(students: dict[str, SimpleNamespace]) -> None:
    dependencies.set_student_manager(SimpleNamespace(students=students))


class TestHealth:
    def test_ok_without_manager(self, client: TestClient) -> None:
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_head(self, client: TestClient) -> None:
        assert client.head("/api/health").status_code == 200


class TestReady:
    def test_starting_before_init(self, client: TestClient) -> None:
        resp = client.get("/api/ready")
        assert resp.status_code == 503
        assert resp.json()["status"] == "starting"

    def test_unconfigured_without_students(self, client: TestClient) -> None:
        _use({})
        resp = client.get("/api/ready")
        assert resp.status_code == 503
        assert resp.json()["status"] == "unconfigured"

    def test_degraded_when_a_student_is_logged_out(self, client: TestClient) -> None:
        _use({"Alice": _ctx(True), "Bob": _ctx(False)})
        resp = client.get("/api/ready")
        assert resp.status_code == 503
        assert resp.json() == {
            "status": "degraded",
            "students": {"Alice": True, "Bob": False},
        }

    def test_ok_when_all_authenticated(self, client: TestClient) -> None:
        _use({"Alice": _ctx(True)})
        resp = client.get("/api/ready")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert client.head("/api/ready").status_code == 200
