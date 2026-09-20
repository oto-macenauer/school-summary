"""Tests for the extraction pipeline: AI response → agenda records → digest."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.config import AgendaConfig, AppConfig
from app.modules.tagging import (
    TAG_SCHEMA_VERSION,
    TaggableMessage,
    TaggingModule,
)
from app.services import scheduler as scheduler_module
from app.services.scheduler import BackgroundScheduler
from app.storage.agenda_storage import AgendaStorage
from app.storage.tag_storage import TagStorage

RESPONSE = {
    "1": {
        "temporal": [{"from": "2026-10-14", "to": None, "label": "písemka"}],
        "subjects": ["Matematika"],
        "importance": ["test"],
        "events": [
            {
                "kind": "test",
                "title": "Písemka z rovnic",
                "date": "2026-10-14",
                "time_from": "08:00",
                "subject": "Matematika",
            }
        ],
        "tasks": [
            {
                "kind": "pay",
                "title": "Záloha na lyžák",
                "due": "2026-10-10",
                "amount": 3500,
                "currency": "CZK",
            }
        ],
    }
}


@pytest.fixture
def message() -> TaggableMessage:
    return TaggableMessage(
        message_id="1234",
        title="Informace k pololetí",
        body="Dne 14. 10. bude písemka, zálohu 3500 Kč uhraďte do 10. 10.",
        sent_date=date(2026, 10, 1),
        source_type="komens",
    )


@pytest.fixture
def tagger() -> TaggingModule:
    gemini = MagicMock()
    gemini.generate_content = AsyncMock()
    return TaggingModule(gemini)


class TestTaggableMessage:
    def test_source_id_matches_the_resources_id(self, message: TaggableMessage) -> None:
        """Agenda records point back at the message via the resources item id."""
        assert message.source_id == "komens-1234"


class TestExtractionParsing:
    def test_events_and_tasks_are_extracted(
        self, tagger: TaggingModule, message: TaggableMessage,
    ) -> None:
        result = tagger._parse_response(json.dumps(RESPONSE), [message])
        extraction = result["1234"]

        assert extraction.tags.subjects == ["Matematika"]
        assert len(extraction.events) == 1
        assert extraction.events[0].title == "Písemka z rovnic"
        assert extraction.events[0].source == "komens-1234"
        assert extraction.events[0].source_category == "komens"
        assert len(extraction.tasks) == 1
        assert extraction.tasks[0].amount == 3500

    def test_missing_agenda_keys_yield_empty_lists(
        self, tagger: TaggingModule, message: TaggableMessage,
    ) -> None:
        """An old-shaped response still produces valid tags."""
        response = {"1": {"temporal": [], "subjects": [], "importance": ["info"]}}
        extraction = tagger._parse_response(json.dumps(response), [message])["1234"]
        assert extraction.events == []
        assert extraction.tasks == []
        assert extraction.tags.importance == ["info"]

    def test_garbage_agenda_entries_are_skipped(
        self, tagger: TaggingModule, message: TaggableMessage,
    ) -> None:
        response = {
            "1": {
                "temporal": [],
                "subjects": [],
                "importance": [],
                "events": [{"kind": "test"}, "junk"],
                "tasks": "nope",
            }
        }
        extraction = tagger._parse_response(json.dumps(response), [message])["1234"]
        assert extraction.events == []
        assert extraction.tasks == []

    @pytest.mark.asyncio
    async def test_tag_messages_returns_extractions(
        self, tagger: TaggingModule, message: TaggableMessage,
    ) -> None:
        tagger._gemini.generate_content.return_value = json.dumps(RESPONSE)
        result = await tagger.tag_messages([message])
        assert result["1234"].events[0].kind == "test"


class TestPromptTemplate:
    def test_placeholders_are_substituted(
        self, tagger: TaggingModule, message: TaggableMessage,
    ) -> None:
        prompt = tagger._build_tagging_prompt([message])
        assert "{today}" not in prompt
        assert "{messages}" not in prompt
        assert date.today().isoformat() in prompt
        assert "1234" in prompt
        assert "Informace k pololetí" in prompt

    def test_json_braces_survive(self, tagger: TaggingModule, message: TaggableMessage) -> None:
        """The template holds a JSON schema — it must not go through str.format."""
        prompt = tagger._build_tagging_prompt([message])
        assert '"events"' in prompt
        assert '"tasks"' in prompt

    def test_custom_template_is_used(self, message: TaggableMessage) -> None:
        gemini = MagicMock()
        tagger = TaggingModule(
            gemini,
            prompt_template="Dnes {today}\n{messages}\nKonec",
            system_instruction="Buď stručný",
        )
        prompt = tagger._build_tagging_prompt([message])
        assert prompt.startswith(f"Dnes {date.today().isoformat()}")
        assert prompt.endswith("Konec")
        assert tagger._get_system_instruction() == "Buď stručný"


def _write_message_file(path: Path, message_id: str, sent: date, tagged: bool) -> Path:
    file_path = path / f"{message_id}.md"
    lines = [
        "---",
        f"message_id: {message_id}",
        "title: Zpráva",
        f"date: {sent.isoformat()}T09:00:00",
    ]
    if tagged:
        lines += [
            'tags_temporal: []',
            'tags_subjects: []',
            'tags_importance: []',
            f"tagged_at: {datetime.now().isoformat()}",
        ]
    lines += ["---", "", "Tělo zprávy."]
    file_path.write_text("\n".join(lines), encoding="utf-8")
    return file_path


class TestSchemaVersioning:
    def test_new_tags_record_the_schema_version(self, tmp_path: Path) -> None:
        path = _write_message_file(tmp_path, "1", date(2026, 10, 1), tagged=False)
        from app.modules.tagging import MessageTags

        TagStorage.write_tags(path, MessageTags(tagged_at=datetime.now()))
        assert TagStorage.read_schema_version(path) == TAG_SCHEMA_VERSION

    def test_untagged_file_is_version_zero(self, tmp_path: Path) -> None:
        path = _write_message_file(tmp_path, "1", date(2026, 10, 1), tagged=False)
        assert TagStorage.read_schema_version(path) == 0

    def test_legacy_tags_are_version_one(self, tmp_path: Path) -> None:
        """Files tagged before versioning carry tags but no agenda records."""
        path = _write_message_file(tmp_path, "1", date(2026, 10, 1), tagged=True)
        assert TagStorage.read_schema_version(path) == 1

    def test_untagged_is_always_processed(self, tmp_path: Path) -> None:
        path = _write_message_file(tmp_path, "1", date(2000, 1, 1), tagged=False)
        cutoff = date.today() - timedelta(days=90)
        assert TagStorage.needs_extraction(path, date(2000, 1, 1), cutoff) is True

    def test_current_schema_is_never_reprocessed(self, tmp_path: Path) -> None:
        from app.modules.tagging import MessageTags

        path = _write_message_file(tmp_path, "1", date.today(), tagged=False)
        TagStorage.write_tags(path, MessageTags(tagged_at=datetime.now()))
        cutoff = date.today() - timedelta(days=90)
        assert TagStorage.needs_extraction(path, date.today(), cutoff) is False

    def test_old_schema_inside_backfill_window_is_reprocessed(self, tmp_path: Path) -> None:
        sent = date.today() - timedelta(days=10)
        path = _write_message_file(tmp_path, "1", sent, tagged=True)
        cutoff = date.today() - timedelta(days=90)
        assert TagStorage.needs_extraction(path, sent, cutoff) is True

    def test_old_schema_outside_backfill_window_is_left_alone(self, tmp_path: Path) -> None:
        sent = date.today() - timedelta(days=200)
        path = _write_message_file(tmp_path, "1", sent, tagged=True)
        cutoff = date.today() - timedelta(days=90)
        assert TagStorage.needs_extraction(path, sent, cutoff) is False

    def test_backfill_disabled_skips_old_schema(self, tmp_path: Path) -> None:
        sent = date.today()
        path = _write_message_file(tmp_path, "1", sent, tagged=True)
        assert TagStorage.needs_extraction(path, sent, None) is False


def _make_scheduler(tmp_path: Path, agenda_cfg: AgendaConfig | None = None):
    """Scheduler wired to real storage in tmp_path and mocked outside world."""
    komens_dir = tmp_path / "komens"
    komens_dir.mkdir()
    agenda_storage = AgendaStorage(tmp_path / "agenda", "Alice")

    ctx = SimpleNamespace(
        name="Alice",
        komens_storage=SimpleNamespace(
            get_saved_files=lambda: sorted(komens_dir.glob("*.md")),
        ),
        mail_storage=SimpleNamespace(get_saved_files=lambda: []),
        gdrive_storage=SimpleNamespace(get_all_reports=lambda: []),
        agenda_storage=agenda_storage,
    )

    gemini = MagicMock()
    gemini.generate_content = AsyncMock(return_value=json.dumps(RESPONSE))
    manager = MagicMock()
    manager.gemini = gemini
    manager.students = {"Alice": ctx}

    config = AppConfig(agenda=agenda_cfg or AgendaConfig())
    push = MagicMock()
    push.send_notification = AsyncMock(return_value=1)

    scheduler = BackgroundScheduler(manager, config, push_service=push)
    return scheduler, ctx, komens_dir, agenda_storage, gemini, push


class TestRefreshTagsWritesAgenda:
    @pytest.mark.asyncio
    async def test_extraction_is_persisted(self, tmp_path: Path) -> None:
        scheduler, ctx, komens_dir, storage, _, _ = _make_scheduler(tmp_path)
        path = _write_message_file(komens_dir, "1234", date(2026, 10, 1), tagged=False)

        await scheduler._refresh_tags(ctx)

        events = storage.load_events()
        tasks = storage.load_tasks()
        assert [e.title for e in events] == ["Písemka z rovnic"]
        assert [t.title for t in tasks] == ["Záloha na lyžák"]
        assert events[0].source == "komens-1234"
        # Tags land in the markdown frontmatter, stamped with the schema
        assert TagStorage.read_schema_version(path) == TAG_SCHEMA_VERSION

    @pytest.mark.asyncio
    async def test_already_current_messages_are_skipped(self, tmp_path: Path) -> None:
        scheduler, ctx, komens_dir, _, gemini, _ = _make_scheduler(tmp_path)
        _write_message_file(komens_dir, "1234", date(2026, 10, 1), tagged=False)

        await scheduler._refresh_tags(ctx)
        assert gemini.generate_content.call_count == 1

        await scheduler._refresh_tags(ctx)
        assert gemini.generate_content.call_count == 1  # nothing left to do

    @pytest.mark.asyncio
    async def test_old_history_stays_out_of_the_backfill(self, tmp_path: Path) -> None:
        scheduler, ctx, komens_dir, _, gemini, _ = _make_scheduler(
            tmp_path, AgendaConfig(backfill_days=30),
        )
        _write_message_file(
            komens_dir, "old", date.today() - timedelta(days=200), tagged=True,
        )

        await scheduler._refresh_tags(ctx)
        gemini.generate_content.assert_not_called()

    @pytest.mark.asyncio
    async def test_re_extraction_keeps_done_state(self, tmp_path: Path) -> None:
        scheduler, ctx, komens_dir, storage, gemini, _ = _make_scheduler(tmp_path)
        _write_message_file(komens_dir, "1234", date(2026, 10, 1), tagged=False)
        await scheduler._refresh_tags(ctx)

        task_id = storage.load_tasks()[0].id
        storage.set_state(task_id, done=True)

        # Message re-processed (e.g. schema bump) — the checkbox must survive
        storage_path = komens_dir / "1234.md"
        content = storage_path.read_text(encoding="utf-8")
        storage_path.write_text(
            content.replace(f"tag_schema: {TAG_SCHEMA_VERSION}", "tag_schema: 1"),
            encoding="utf-8",
        )
        await scheduler._refresh_tags(ctx)

        assert storage.get_state(task_id).done is True

    @pytest.mark.asyncio
    async def test_no_gemini_is_a_no_op(self, tmp_path: Path) -> None:
        scheduler, ctx, komens_dir, storage, _, _ = _make_scheduler(tmp_path)
        scheduler._manager.gemini = None
        _write_message_file(komens_dir, "1234", date(2026, 10, 1), tagged=False)

        await scheduler._refresh_tags(ctx)
        assert storage.load_events() == []


class _FrozenDatetime:
    """Stand-in for datetime.now() inside the scheduler module."""

    fixed = datetime(2026, 10, 13, 19, 0, 0)

    @classmethod
    def now(cls) -> datetime:
        return cls.fixed


class TestAgendaDigest:
    @pytest.fixture
    def frozen(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(scheduler_module, "datetime", _FrozenDatetime)
        return _FrozenDatetime.fixed

    def _seed(self, storage: AgendaStorage) -> None:
        from app.modules.agenda import parse_events, parse_tasks

        storage.replace_source(
            "komens-1",
            parse_events(
                [
                    {"kind": "test", "title": "Písemka", "date": "2026-10-14"},
                    {"kind": "event", "title": "Za týden", "date": "2026-10-20"},
                ],
                "komens-1", "komens", datetime(2026, 10, 1),
            ),
            parse_tasks(
                [
                    {"kind": "pay", "title": "Záloha", "due": "2026-10-14"},
                    {"kind": "buy", "title": "Daleko", "due": "2026-11-30"},
                ],
                "komens-1", "komens", datetime(2026, 10, 1),
            ),
        )

    @pytest.mark.asyncio
    async def test_sends_tomorrows_events_and_due_tasks(
        self, tmp_path: Path, frozen: datetime,
    ) -> None:
        scheduler, ctx, _, storage, _, push = _make_scheduler(tmp_path)
        self._seed(storage)

        await scheduler._agenda_digest(ctx)

        push.send_notification.assert_awaited_once()
        body = push.send_notification.await_args.kwargs["body"]
        assert "Písemka" in body
        assert "Záloha" in body
        assert "Za týden" not in body
        assert "Daleko" not in body
        assert storage.last_digest_date() == frozen.date()

    @pytest.mark.asyncio
    async def test_only_once_a_day(self, tmp_path: Path, frozen: datetime) -> None:
        scheduler, ctx, _, storage, _, push = _make_scheduler(tmp_path)
        self._seed(storage)

        await scheduler._agenda_digest(ctx)
        await scheduler._agenda_digest(ctx)

        assert push.send_notification.await_count == 1

    @pytest.mark.asyncio
    async def test_waits_for_the_configured_hour(
        self, tmp_path: Path, frozen: datetime,
    ) -> None:
        scheduler, ctx, _, storage, _, push = _make_scheduler(
            tmp_path, AgendaConfig(reminder_hour=20),
        )
        self._seed(storage)

        await scheduler._agenda_digest(ctx)

        push.send_notification.assert_not_awaited()
        assert storage.last_digest_date() is None

    @pytest.mark.asyncio
    async def test_disabled_sends_nothing(self, tmp_path: Path, frozen: datetime) -> None:
        scheduler, ctx, _, storage, _, push = _make_scheduler(
            tmp_path, AgendaConfig(reminder_enabled=False),
        )
        self._seed(storage)

        await scheduler._agenda_digest(ctx)
        push.send_notification.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_done_and_dismissed_are_left_out(
        self, tmp_path: Path, frozen: datetime,
    ) -> None:
        scheduler, ctx, _, storage, _, push = _make_scheduler(tmp_path)
        self._seed(storage)
        storage.set_state("komens-1-t0", done=True)
        storage.set_state("komens-1-e0", dismissed=True)

        await scheduler._agenda_digest(ctx)

        push.send_notification.assert_not_awaited()
        # The day is still marked, so the check stays cheap until tomorrow
        assert storage.last_digest_date() == frozen.date()

    @pytest.mark.asyncio
    async def test_nothing_scheduled_sends_nothing(
        self, tmp_path: Path, frozen: datetime,
    ) -> None:
        scheduler, ctx, _, storage, _, push = _make_scheduler(tmp_path)

        await scheduler._agenda_digest(ctx)

        push.send_notification.assert_not_awaited()
        assert storage.last_digest_date() == frozen.date()

    @pytest.mark.asyncio
    async def test_long_lists_are_summarised(
        self, tmp_path: Path, frozen: datetime,
    ) -> None:
        from app.modules.agenda import parse_events

        scheduler, ctx, _, storage, _, push = _make_scheduler(tmp_path)
        storage.replace_source(
            "komens-1",
            parse_events(
                [
                    {"title": f"Akce {i}", "date": "2026-10-14"}
                    for i in range(5)
                ],
                "komens-1", "komens", datetime(2026, 10, 1),
            ),
            [],
        )

        await scheduler._agenda_digest(ctx)

        body = push.send_notification.await_args.kwargs["body"]
        assert "+2 další" in body

    @pytest.mark.asyncio
    async def test_multi_day_event_running_tomorrow_is_included(
        self, tmp_path: Path, frozen: datetime,
    ) -> None:
        from app.modules.agenda import parse_events

        scheduler, ctx, _, storage, _, push = _make_scheduler(tmp_path)
        storage.replace_source(
            "komens-1",
            parse_events(
                [{"kind": "trip", "title": "Lyžák", "date": "2026-10-12", "date_to": "2026-10-18"}],
                "komens-1", "komens", datetime(2026, 10, 1),
            ),
            [],
        )

        await scheduler._agenda_digest(ctx)

        assert "Lyžák" in push.send_notification.await_args.kwargs["body"]

    @pytest.mark.asyncio
    async def test_without_push_service_nothing_happens(self, tmp_path: Path, frozen: datetime) -> None:
        scheduler, ctx, _, storage, _, _ = _make_scheduler(tmp_path)
        scheduler._push_service = None
        self._seed(storage)

        await scheduler._agenda_digest(ctx)
        assert storage.last_digest_date() is None
