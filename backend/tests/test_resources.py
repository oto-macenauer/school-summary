"""Tests for the paged resources endpoint and the dashboard's resources feed."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from app import dependencies
from app.api import resources as resources_api
from app.api.dashboard import PREVIEW_CHARS, _preview
from app.main import app
from app.storage.agenda_storage import AgendaStorage

STUDENT = "Alice"
URL = f"/api/students/{STUDENT}/resources"


def _write(
    path: Path,
    *,
    message_id: str,
    title: str,
    date: str,
    body: str = "Text zprávy",
    read: bool | None = None,
    importance: str | None = None,
    subjects: str | None = None,
) -> Path:
    lines = [f"message_id: {message_id}", f'title: "{title}"', "sender: Učitel", f"date: {date}"]
    if read is not None:
        lines.append(f"read: {'true' if read else 'false'}")
    if importance or subjects:
        lines.append("tagged_at: 2026-09-01T10:00:00")
        lines.append(f"tags_importance: {json.dumps([importance] if importance else [])}")
        lines.append(f"tags_subjects: {json.dumps([subjects] if subjects else [])}")
    # Komens bodies carry a markdown header block the endpoint strips
    header = f"# {title}\n\n---\n" if path.parent.name == "komens" else ""
    path.write_text(
        "---\n" + "\n".join(lines) + f"\n---\n{header}{body}\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def dirs(tmp_path: Path) -> dict[str, Path]:
    out = {k: tmp_path / k for k in ("komens", "mail", "reports")}
    for d in out.values():
        d.mkdir()
    return out


@pytest.fixture
def ctx(dirs: dict[str, Path], tmp_path: Path) -> SimpleNamespace:
    # 40 komens messages, oldest first: komens-0 .. komens-39
    for i in range(40):
        _write(
            dirs["komens"] / f"k{i}.md",
            message_id=str(i),
            title=f"Komens {i}",
            date=f"2026-09-{1 + i % 28:02d}T{8 + i // 28:02d}:00:00",
            read=i % 2 == 0,
            importance="test" if i % 10 == 0 else None,
            subjects="Matematika" if i % 10 == 0 else None,
        )
    _write(dirs["mail"] / "m1.md", message_id="m1", title="Mail o výletu", date="2026-09-30T12:00:00", body="Jedeme do Brna")

    return SimpleNamespace(
        name=STUDENT,
        komens_storage=SimpleNamespace(get_saved_files=lambda: sorted(dirs["komens"].glob("*.md"))),
        mail_storage=SimpleNamespace(storage_path=dirs["mail"]),
        gdrive_storage=SimpleNamespace(get_all_reports=lambda: []),
        agenda_storage=AgendaStorage(tmp_path / "agenda", STUDENT),
        timetable=None,
        summary_last=None,
        summary_current=None,
        summary_next=None,
        marks=None,
        prepare_today=None,
        prepare_tomorrow=None,
    )


@pytest.fixture
def client(ctx: SimpleNamespace) -> Iterator[TestClient]:
    resources_api._parse_cache.clear()
    manager = SimpleNamespace(
        config=None,
        get_student=lambda name: ctx if name.lower() == STUDENT.lower() else None,
    )
    dependencies.set_student_manager(manager)
    yield TestClient(app)
    dependencies.set_student_manager(None)
    resources_api._parse_cache.clear()


class TestPaging:
    def test_first_page(self, client: TestClient) -> None:
        data = client.get(URL, params={"limit": 10}).json()
        assert len(data["items"]) == 10
        assert data["total"] == 41
        assert data["offset"] == 0
        assert data["has_more"] is True
        # Newest first: the mail is dated after every komens message
        assert data["items"][0]["id"] == "mail-m1"

    def test_pages_cover_everything_without_overlap(self, client: TestClient) -> None:
        seen: list[str] = []
        offset = 0
        while True:
            data = client.get(URL, params={"offset": offset, "limit": 15}).json()
            seen += [i["id"] for i in data["items"]]
            offset += len(data["items"])
            if not data["has_more"]:
                break
        assert len(seen) == 41
        assert len(set(seen)) == 41
        dates = [
            i["date"] for i in client.get(URL, params={"limit": 100}).json()["items"]
        ]
        assert dates == sorted(dates, reverse=True)

    def test_offset_past_end_is_empty(self, client: TestClient) -> None:
        data = client.get(URL, params={"offset": 500}).json()
        assert data["items"] == []
        assert data["has_more"] is False

    def test_limit_is_bounded(self, client: TestClient) -> None:
        assert client.get(URL, params={"limit": 0}).status_code == 422
        assert client.get(URL, params={"limit": 1000}).status_code == 422

    def test_unknown_student(self, client: TestClient) -> None:
        assert client.get("/api/students/Bob/resources").status_code == 404


class TestFilters:
    def test_category(self, client: TestClient) -> None:
        data = client.get(URL, params={"category": "mail"}).json()
        assert [i["id"] for i in data["items"]] == ["mail-m1"]
        assert data["total"] == 1
        # Category pills still count every category
        assert data["counts"] == {"all": 41, "komens": 40, "mail": 1, "report": 0}

    def test_importance_and_subject(self, client: TestClient) -> None:
        for params in ({"importance": "test"}, {"subject": "Matematika"}):
            data = client.get(URL, params=params).json()
            assert {i["id"] for i in data["items"]} == {"komens-0", "komens-10", "komens-20", "komens-30"}
            assert data["counts"]["all"] == 4

    def test_search_matches_title_sender_and_body(self, client: TestClient) -> None:
        assert [i["id"] for i in client.get(URL, params={"q": "brna"}).json()["items"]] == ["mail-m1"]
        assert [i["id"] for i in client.get(URL, params={"q": "KOMENS 39"}).json()["items"]] == ["komens-39"]
        assert client.get(URL, params={"q": "učitel"}).json()["total"] == 41

    def test_unread_count_and_tags(self, client: TestClient) -> None:
        data = client.get(URL, params={"category": "mail"}).json()
        # Unread and tags describe the whole store, not the filtered page
        assert data["unread_count"] == 20
        assert data["available_tags"] == {"subjects": ["Matematika"], "importance": ["test"]}


class TestParseCache:
    def test_reparses_changed_file(self, client: TestClient, dirs: dict[str, Path]) -> None:
        client.get(URL)
        path = dirs["mail"] / "m1.md"
        _write(path, message_id="m1", title="Nový název", date="2026-09-30T12:00:00")
        stat = path.stat()
        os.utime(path, (stat.st_atime, stat.st_mtime + 10))
        items = client.get(URL, params={"category": "mail"}).json()["items"]
        assert items[0]["title"] == "Nový název"

    def test_deleted_file_disappears(self, client: TestClient, dirs: dict[str, Path]) -> None:
        client.get(URL)
        (dirs["mail"] / "m1.md").unlink()
        assert client.get(URL, params={"category": "mail"}).json()["total"] == 0


class TestDashboardFeed:
    def test_recent_resources_of_every_kind(self, client: TestClient) -> None:
        data = client.get(f"/api/students/{STUDENT}/dashboard").json()["resources"]
        assert data["total"] == 41
        assert data["unread_count"] == 20
        assert len(data["recent"]) == 5
        first = data["recent"][0]
        assert first["id"] == "mail-m1"
        assert first["category"] == "mail"
        assert first["preview"] == "Jedeme do Brna"
        assert "body" not in first

    def test_preview_truncates_and_flattens(self) -> None:
        assert _preview("a\n\n  b", False) == "a b"
        long = _preview("x" * 500, False)
        assert len(long) == PREVIEW_CHARS + 1
        assert long.endswith("…")

    def test_preview_strips_markdown_markers(self) -> None:
        assert _preview("## Nadpis\n- **tučně** bod\n1. druhý", True) == "Nadpis tučně bod druhý"
