"""Tests for BackgroundScheduler service."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.config import AppConfig, UpdateIntervalsConfig
from app.modules.prepare import PrepareData
from app.modules.summary import (
    SummaryData,
    get_last_week_range,
    get_next_week_range,
)
from app.services.scheduler import BackgroundScheduler, TaskStatus
from app.services.student_manager import StudentContext


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_student_context() -> MagicMock:
    """Create a mock StudentContext with None data fields."""
    ctx = MagicMock(spec=StudentContext)
    ctx.name = "TestStudent"
    ctx.timetable = None
    ctx.timetable_last = None
    ctx.timetable_next = None
    ctx.marks = None
    ctx.komens = None
    ctx.timetable_module = AsyncMock()
    ctx.marks_module = AsyncMock()
    ctx.komens_module = AsyncMock()
    ctx.summary_module = MagicMock()
    ctx.prepare_module = MagicMock()
    ctx.komens_storage = MagicMock()
    ctx.gdrive_storage = MagicMock()
    ctx.ai_storage = MagicMock()
    ctx.ai_storage.load_all.return_value = {}
    ctx.ai_storage.save_summary = MagicMock()
    ctx.ai_storage.save_prepare = MagicMock()
    ctx.gdrive_client = None
    ctx.timetable_updated = None
    ctx.marks_updated = None
    ctx.komens_updated = None
    ctx.summary_updated = None
    ctx.prepare_updated = None
    ctx.summary_current = None
    ctx.summary_last = None
    ctx.summary_next = None
    ctx.prepare_today = None
    ctx.prepare_tomorrow = None
    ctx.student_info = ""
    return ctx


@pytest.fixture
def mock_manager(mock_student_context) -> MagicMock:
    """Create a mock StudentManager."""
    manager = MagicMock()
    manager.students = {"TestStudent": mock_student_context}
    manager.gemini = MagicMock()
    manager.canteen_module = None
    return manager


@pytest.fixture
def config() -> AppConfig:
    """Create a test AppConfig with short intervals."""
    return AppConfig(
        base_url="https://test.school.cz",
        update_intervals=UpdateIntervalsConfig(
            timetable=10,
            marks=10,
            komens=10,
            summary=60,
            prepare=60,
            gdrive=60,
        ),
    )


@pytest.fixture
def scheduler(mock_manager, config) -> BackgroundScheduler:
    """Create a BackgroundScheduler instance."""
    return BackgroundScheduler(mock_manager, config)


# ---------------------------------------------------------------------------
# TaskStatus tests
# ---------------------------------------------------------------------------

class TestTaskStatus:
    """Tests for TaskStatus dataclass."""

    def test_default_values(self):
        """Test initial state of TaskStatus."""
        status = TaskStatus(task_name="timetable", student="Test", interval_seconds=60)
        assert status.last_run is None
        assert status.last_duration_ms is None
        assert status.last_status == "pending"
        assert status.last_error is None
        assert status.run_count == 0
        assert status.error_count == 0

    def test_to_dict(self):
        """Test TaskStatus serialization."""
        now = datetime(2024, 12, 15, 10, 0, 0)
        status = TaskStatus(
            task_name="marks",
            student="Test",
            interval_seconds=30,
            last_run=now,
            last_duration_ms=150,
            last_status="success",
            run_count=5,
        )
        d = status.to_dict()
        assert d["task_name"] == "marks"
        assert d["student"] == "Test"
        assert d["interval_seconds"] == 30
        assert d["last_run"] == now.isoformat()
        assert d["last_duration_ms"] == 150
        assert d["last_status"] == "success"
        assert d["run_count"] == 5

    def test_to_dict_with_none_dates(self):
        """Test serialization when datetime fields are None."""
        status = TaskStatus(task_name="timetable", student="Test", interval_seconds=60)
        d = status.to_dict()
        assert d["last_run"] is None
        assert d["next_run"] is None


# ---------------------------------------------------------------------------
# _wait_for_data tests
# ---------------------------------------------------------------------------

class TestWaitForData:
    """Tests for the _wait_for_data dependency waiting method."""

    @pytest.mark.asyncio
    async def test_returns_true_when_data_already_present(self, scheduler, mock_student_context):
        """Should return True immediately when data is already available."""
        scheduler._running = True
        mock_student_context.timetable = MagicMock()
        mock_student_context.marks = MagicMock()

        result = await scheduler._wait_for_data(
            mock_student_context, poll_interval=0.05, timeout=1.0,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_true_when_data_arrives_during_poll(self, scheduler, mock_student_context):
        """Should return True when data arrives while polling."""
        scheduler._running = True

        async def populate_data():
            await asyncio.sleep(0.1)
            mock_student_context.timetable = MagicMock()
            mock_student_context.marks = MagicMock()

        asyncio.create_task(populate_data())
        result = await scheduler._wait_for_data(
            mock_student_context, poll_interval=0.05, timeout=2.0,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_on_timeout(self, scheduler, mock_student_context):
        """Should return False when timeout is reached."""
        scheduler._running = True

        result = await scheduler._wait_for_data(
            mock_student_context, poll_interval=0.05, timeout=0.15,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_not_running(self, scheduler, mock_student_context):
        """Should return False promptly when scheduler is not running."""
        scheduler._running = False

        result = await scheduler._wait_for_data(
            mock_student_context, poll_interval=0.05, timeout=2.0,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_only_checks_timetable_when_marks_not_needed(self, scheduler, mock_student_context):
        """Should return True when only timetable is needed and available."""
        scheduler._running = True
        mock_student_context.timetable = MagicMock()
        # marks is still None

        result = await scheduler._wait_for_data(
            mock_student_context, needs_marks=False, poll_interval=0.05, timeout=1.0,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_only_checks_marks_when_timetable_not_needed(self, scheduler, mock_student_context):
        """Should return True when only marks is needed and available."""
        scheduler._running = True
        mock_student_context.marks = MagicMock()
        # timetable is still None

        result = await scheduler._wait_for_data(
            mock_student_context, needs_timetable=False, poll_interval=0.05, timeout=1.0,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_handles_cancellation(self, scheduler, mock_student_context):
        """Should return False when task is cancelled during wait."""
        scheduler._running = True

        async def cancel_soon(task):
            await asyncio.sleep(0.1)
            task.cancel()

        task = asyncio.create_task(
            scheduler._wait_for_data(mock_student_context, poll_interval=0.05, timeout=10.0)
        )
        asyncio.create_task(cancel_soon(task))

        result = await task
        assert result is False


# ---------------------------------------------------------------------------
# _refresh_summary wait tests
# ---------------------------------------------------------------------------

class TestRefreshSummaryWait:
    """Tests for dependency waiting in _refresh_summary."""

    @pytest.mark.asyncio
    async def test_summary_waits_when_data_is_none(self, scheduler, mock_student_context):
        """Should call _wait_for_data when timetable/marks are None."""
        scheduler._running = True

        with patch.object(scheduler, "_wait_for_data", new_callable=AsyncMock, return_value=True) as mock_wait:
            # Make gemini.generate_content return something
            scheduler._manager.gemini.generate_content = AsyncMock(return_value="summary text")
            mock_student_context.summary_module.get_week_messages.return_value = []
            mock_student_context.summary_module.extract_new_marks.return_value = []
            mock_student_context.summary_module.build_prompt_from_template.return_value = "prompt"
            mock_student_context.gdrive_client = None

            await scheduler._refresh_summary(mock_student_context)

            mock_wait.assert_called_once_with(
                mock_student_context, needs_timetable=True, needs_marks=True,
            )

    @pytest.mark.asyncio
    async def test_summary_skips_wait_when_data_present(self, scheduler, mock_student_context):
        """Should not call _wait_for_data when data is already present."""
        scheduler._running = True
        mock_student_context.timetable = MagicMock()
        mock_student_context.marks = MagicMock()

        with patch.object(scheduler, "_wait_for_data", new_callable=AsyncMock) as mock_wait:
            scheduler._manager.gemini.generate_content = AsyncMock(return_value="summary text")
            mock_student_context.summary_module.get_week_messages.return_value = []
            mock_student_context.summary_module.extract_new_marks.return_value = []
            mock_student_context.summary_module.build_prompt_from_template.return_value = "prompt"
            mock_student_context.gdrive_client = None

            await scheduler._refresh_summary(mock_student_context)

            mock_wait.assert_not_called()

    @pytest.mark.asyncio
    async def test_summary_proceeds_after_timeout(self, scheduler, mock_student_context):
        """Should not raise even if _wait_for_data times out."""
        scheduler._running = True

        with patch.object(scheduler, "_wait_for_data", new_callable=AsyncMock, return_value=False):
            scheduler._manager.gemini.generate_content = AsyncMock(return_value="summary text")
            mock_student_context.summary_module.get_week_messages.return_value = []
            mock_student_context.summary_module.extract_new_marks.return_value = []
            mock_student_context.summary_module.build_prompt_from_template.return_value = "prompt"
            mock_student_context.gdrive_client = None

            # Should not raise
            await scheduler._refresh_summary(mock_student_context)

    @pytest.mark.asyncio
    async def test_summary_skips_when_no_gemini(self, scheduler, mock_student_context):
        """Should return early when Gemini is not configured."""
        scheduler._manager.gemini = None

        with patch.object(scheduler, "_wait_for_data", new_callable=AsyncMock) as mock_wait:
            await scheduler._refresh_summary(mock_student_context)
            mock_wait.assert_not_called()


# ---------------------------------------------------------------------------
# _refresh_prepare wait tests
# ---------------------------------------------------------------------------

class TestRefreshPrepareWait:
    """Tests for dependency waiting in _refresh_prepare."""

    @pytest.mark.asyncio
    async def test_prepare_waits_when_timetable_is_none(self, scheduler, mock_student_context):
        """Should call _wait_for_data when timetable is None."""
        scheduler._running = True

        with patch.object(scheduler, "_wait_for_data", new_callable=AsyncMock, return_value=True) as mock_wait:
            scheduler._manager.gemini.generate_content = AsyncMock(return_value="prep text")
            mock_student_context.prepare_module.get_relevant_messages.return_value = []
            mock_student_context.prepare_module.build_prompt_from_template.return_value = "prompt"
            mock_student_context.prepare_module.format_lessons.return_value = ("", 0)

            await scheduler._refresh_prepare(mock_student_context)

            mock_wait.assert_called_once_with(
                mock_student_context, needs_timetable=True, needs_marks=False,
            )

    @pytest.mark.asyncio
    async def test_prepare_skips_wait_when_timetable_present(self, scheduler, mock_student_context):
        """Should not call _wait_for_data when timetable is present."""
        scheduler._running = True
        mock_student_context.timetable = MagicMock()

        with patch.object(scheduler, "_wait_for_data", new_callable=AsyncMock) as mock_wait:
            scheduler._manager.gemini.generate_content = AsyncMock(return_value="prep text")
            mock_student_context.prepare_module.get_relevant_messages.return_value = []
            mock_student_context.prepare_module.build_prompt_from_template.return_value = "prompt"
            mock_student_context.prepare_module.format_lessons.return_value = ("", 0)

            await scheduler._refresh_prepare(mock_student_context)

            mock_wait.assert_not_called()

    @pytest.mark.asyncio
    async def test_prepare_proceeds_after_timeout(self, scheduler, mock_student_context):
        """Should not raise even if _wait_for_data times out."""
        scheduler._running = True

        with patch.object(scheduler, "_wait_for_data", new_callable=AsyncMock, return_value=False):
            scheduler._manager.gemini.generate_content = AsyncMock(return_value="prep text")
            mock_student_context.prepare_module.get_relevant_messages.return_value = []
            mock_student_context.prepare_module.build_prompt_from_template.return_value = "prompt"
            mock_student_context.prepare_module.format_lessons.return_value = ("", 0)

            await scheduler._refresh_prepare(mock_student_context)

    @pytest.mark.asyncio
    async def test_prepare_skips_when_no_gemini(self, scheduler, mock_student_context):
        """Should return early when Gemini is not configured."""
        scheduler._manager.gemini = None

        with patch.object(scheduler, "_wait_for_data", new_callable=AsyncMock) as mock_wait:
            await scheduler._refresh_prepare(mock_student_context)
            mock_wait.assert_not_called()


# ---------------------------------------------------------------------------
# Prompt dedup tests
# ---------------------------------------------------------------------------

class TestPromptDedup:
    """Tests for prompt-based deduplication in AI tasks."""

    @pytest.mark.asyncio
    async def test_summary_skips_when_prompt_unchanged(self, scheduler, mock_student_context):
        """Should skip Gemini call when prompt hasn't changed since last run."""
        scheduler._running = True
        mock_student_context.timetable = MagicMock()
        mock_student_context.marks = MagicMock()
        mock_student_context.gdrive_client = None

        mock_student_context.summary_module.get_week_messages.return_value = []
        mock_student_context.summary_module.extract_new_marks.return_value = []
        mock_student_context.summary_module.build_prompt_from_template.return_value = "same prompt"

        gemini_mock = AsyncMock(return_value="summary text")
        scheduler._manager.gemini.generate_content = gemini_mock

        # First call — should call Gemini
        await scheduler._refresh_summary(mock_student_context)
        assert gemini_mock.call_count == 3  # last, current, next

        # Second call — same prompt, should skip all 3
        gemini_mock.reset_mock()
        await scheduler._refresh_summary(mock_student_context)
        assert gemini_mock.call_count == 0

    @pytest.mark.asyncio
    async def test_summary_calls_when_prompt_changes(self, scheduler, mock_student_context):
        """Should call Gemini again when prompt changes."""
        scheduler._running = True
        mock_student_context.timetable = MagicMock()
        mock_student_context.marks = MagicMock()
        mock_student_context.gdrive_client = None

        mock_student_context.summary_module.get_week_messages.return_value = []
        mock_student_context.summary_module.extract_new_marks.return_value = []
        mock_student_context.summary_module.build_prompt_from_template.return_value = "prompt v1"

        gemini_mock = AsyncMock(return_value="summary text")
        scheduler._manager.gemini.generate_content = gemini_mock

        # First run
        await scheduler._refresh_summary(mock_student_context)
        assert gemini_mock.call_count == 3

        # Change prompt
        gemini_mock.reset_mock()
        mock_student_context.summary_module.build_prompt_from_template.return_value = "prompt v2"
        await scheduler._refresh_summary(mock_student_context)
        assert gemini_mock.call_count == 3

    @pytest.mark.asyncio
    async def test_prepare_skips_when_prompt_unchanged(self, scheduler, mock_student_context):
        """Should skip Gemini call for prepare when prompt hasn't changed."""
        scheduler._running = True
        mock_student_context.timetable = MagicMock()

        mock_student_context.prepare_module.get_relevant_messages.return_value = []
        mock_student_context.prepare_module.build_prompt_from_template.return_value = "same prompt"
        mock_student_context.prepare_module.format_lessons.return_value = ("", 0)

        gemini_mock = AsyncMock(return_value="prep text")
        scheduler._manager.gemini.generate_content = gemini_mock

        # First call — should call Gemini
        await scheduler._refresh_prepare(mock_student_context)
        assert gemini_mock.call_count == 2  # today, tomorrow

        # Second call — same prompt, should skip both
        gemini_mock.reset_mock()
        await scheduler._refresh_prepare(mock_student_context)
        assert gemini_mock.call_count == 0

    @pytest.mark.asyncio
    async def test_prepare_calls_when_prompt_changes(self, scheduler, mock_student_context):
        """Should call Gemini again for prepare when prompt changes."""
        scheduler._running = True
        mock_student_context.timetable = MagicMock()

        mock_student_context.prepare_module.get_relevant_messages.return_value = []
        mock_student_context.prepare_module.build_prompt_from_template.return_value = "prompt v1"
        mock_student_context.prepare_module.format_lessons.return_value = ("", 0)

        gemini_mock = AsyncMock(return_value="prep text")
        scheduler._manager.gemini.generate_content = gemini_mock

        # First run
        await scheduler._refresh_prepare(mock_student_context)
        assert gemini_mock.call_count == 2

        # Change prompt
        gemini_mock.reset_mock()
        mock_student_context.prepare_module.build_prompt_from_template.return_value = "prompt v2"
        await scheduler._refresh_prepare(mock_student_context)
        assert gemini_mock.call_count == 2


# ---------------------------------------------------------------------------
# Scheduler lifecycle tests
# ---------------------------------------------------------------------------

class TestSchedulerLifecycle:
    """Tests for scheduler start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_creates_tasks(self, scheduler):
        """Starting the scheduler should create async tasks."""
        await scheduler.start()
        # One asyncio task per registered task key
        assert len(scheduler._tasks) == len(scheduler._task_statuses)
        assert {"timetable:TestStudent", "marks:TestStudent"} <= set(
            scheduler._task_statuses
        )
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_tasks(self, scheduler):
        """Stopping should cancel all tasks and clear the list."""
        await scheduler.start()
        assert len(scheduler._tasks) > 0
        await scheduler.stop()
        assert len(scheduler._tasks) == 0
        assert scheduler._running is False

    @pytest.mark.asyncio
    async def test_task_statuses_populated(self, scheduler):
        """Task statuses should be created for each scheduled task."""
        await scheduler.start()
        expected_keys = {
            "timetable:TestStudent",
            "marks:TestStudent",
            "komens:TestStudent",
            "summary:TestStudent",
            "prepare:TestStudent",
        }
        # Optional tasks (gdrive, mail, tagging, agenda digest) depend on what
        # the student has configured, so the core set is a subset.
        assert expected_keys <= set(scheduler._task_statuses.keys())
        for status in scheduler._task_statuses.values():
            assert status.last_status == "pending"
            assert status.next_run is not None
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_get_task_status(self, scheduler):
        """Should return task status by key."""
        await scheduler.start()
        status = scheduler.get_task_status("timetable:TestStudent")
        assert status is not None
        assert status.task_name == "timetable"
        assert status.student == "TestStudent"
        assert scheduler.get_task_status("nonexistent") is None
        await scheduler.stop()


# ---------------------------------------------------------------------------
# AI cache persistence tests
# ---------------------------------------------------------------------------

class TestAICachePersistence:
    """Tests for loading cached AI data on start and saving after generation."""

    @pytest.mark.asyncio
    async def test_start_loads_cached_ai_data(self, scheduler, mock_student_context):
        """start() should load cached summaries/preparations into contexts and _last_prompts."""
        summary = SummaryData(
            student_name="TestStudent",
            week_start=date(2026, 3, 2),
            week_end=date(2026, 3, 8),
            summary_text="Cached summary",
            messages_count=3,
            marks_count=1,
            week_type="current",
            generated_at=datetime(2026, 3, 8, 14, 0, 0),
        )
        prepare = PrepareData(
            student_name="TestStudent",
            target_date=date(2026, 3, 9),
            preparation_text="Cached prep",
            lessons_count=5,
            messages_count=2,
            period="today",
            generated_at=datetime(2026, 3, 8, 14, 0, 0),
        )
        mock_student_context.ai_storage.load_all.return_value = {
            "summary:current": (summary, "shash123"),
            "prepare:today": (prepare, "phash456"),
        }

        await scheduler.start()

        # Verify data was set on context
        assert mock_student_context.summary_current == summary
        assert mock_student_context.prepare_today == prepare

        # Verify _last_prompts were seeded
        assert scheduler._last_prompts["summary:TestStudent:current"] == "shash123"
        assert scheduler._last_prompts["prepare:TestStudent:today"] == "phash456"

        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_start_handles_empty_cache(self, scheduler, mock_student_context):
        """start() should work fine when no cached data exists."""
        mock_student_context.ai_storage.load_all.return_value = {}

        await scheduler.start()

        assert "summary:TestStudent:current" not in scheduler._last_prompts
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_refresh_summary_saves_to_ai_storage(self, scheduler, mock_student_context):
        """_refresh_summary should call ai_storage.save_summary after Gemini call."""
        scheduler._running = True
        mock_student_context.timetable = MagicMock()
        mock_student_context.marks = MagicMock()
        mock_student_context.gdrive_client = None

        mock_student_context.summary_module.get_week_messages.return_value = []
        mock_student_context.summary_module.extract_new_marks.return_value = []
        mock_student_context.summary_module.build_prompt_from_template.return_value = "test prompt"

        scheduler._manager.gemini.generate_content = AsyncMock(return_value="generated summary")

        await scheduler._refresh_summary(mock_student_context)

        # Should have been called 3 times (last, current, next)
        assert mock_student_context.ai_storage.save_summary.call_count == 3

        # Verify the hash is a SHA256 digest
        call_args = mock_student_context.ai_storage.save_summary.call_args_list[0]
        saved_hash = call_args[0][1]  # second positional arg is prompt_hash
        assert len(saved_hash) == 64  # SHA256 hex digest length

    @pytest.mark.asyncio
    async def test_refresh_prepare_saves_to_ai_storage(self, scheduler, mock_student_context):
        """_refresh_prepare should call ai_storage.save_prepare after Gemini call."""
        scheduler._running = True
        mock_student_context.timetable = MagicMock()

        mock_student_context.prepare_module.get_relevant_messages.return_value = []
        mock_student_context.prepare_module.build_prompt_from_template.return_value = "test prompt"
        mock_student_context.prepare_module.format_lessons.return_value = ("", 0)

        scheduler._manager.gemini.generate_content = AsyncMock(return_value="generated prep")

        await scheduler._refresh_prepare(mock_student_context)

        # Should have been called 2 times (today, tomorrow)
        assert mock_student_context.ai_storage.save_prepare.call_count == 2

    @pytest.mark.asyncio
    async def test_summary_uses_hash_for_dedup(self, scheduler, mock_student_context):
        """Dedup should use SHA256 hash, not raw prompt fingerprint."""
        scheduler._running = True
        mock_student_context.timetable = MagicMock()
        mock_student_context.marks = MagicMock()
        mock_student_context.gdrive_client = None

        mock_student_context.summary_module.get_week_messages.return_value = []
        mock_student_context.summary_module.extract_new_marks.return_value = []
        mock_student_context.summary_module.build_prompt_from_template.return_value = "prompt"

        gemini_mock = AsyncMock(return_value="text")
        scheduler._manager.gemini.generate_content = gemini_mock

        await scheduler._refresh_summary(mock_student_context)

        # Verify stored values are SHA256 hashes (64 hex chars), not raw prompts
        for key, value in scheduler._last_prompts.items():
            if key.startswith("summary:"):
                assert len(value) == 64
                # Should match expected hash
                system = scheduler._config.prompts.summary_system or ""
                expected = hashlib.sha256(
                    ("prompt" + "\0" + system).encode()
                ).hexdigest()
                assert value == expected


# ---------------------------------------------------------------------------
# Trigger task tests
# ---------------------------------------------------------------------------

class TestTriggerTask:
    """Tests for on-demand task triggering."""

    @pytest.mark.asyncio
    async def test_trigger_registered_task(self, scheduler, mock_student_context):
        """Triggering a registered task should run it and update status."""
        await scheduler.start()

        mock_student_context.timetable_module.get_actual_timetable = AsyncMock(return_value=MagicMock())

        result = await scheduler.trigger_task("timetable:TestStudent")
        assert result is True

        status = scheduler.get_task_status("timetable:TestStudent")
        assert status.last_status == "success"
        assert status.last_duration_ms is not None
        assert status.run_count >= 1

        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_trigger_unknown_task_returns_false(self, scheduler):
        """Triggering an unknown task key should return False."""
        result = await scheduler.trigger_task("nonexistent:nobody")
        assert result is False

    @pytest.mark.asyncio
    async def test_trigger_failing_task_raises(self, scheduler, mock_student_context):
        """Triggering a task that raises should propagate the error."""
        await scheduler.start()

        mock_student_context.timetable_module.get_actual_timetable = AsyncMock(
            side_effect=RuntimeError("API down")
        )

        with pytest.raises(RuntimeError, match="API down"):
            await scheduler.trigger_task("timetable:TestStudent")

        status = scheduler.get_task_status("timetable:TestStudent")
        assert status.last_status == "error"
        assert "API down" in (status.last_error or "")

        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_get_task_keys(self, scheduler):
        """get_task_keys should return all registered task keys."""
        await scheduler.start()
        keys = scheduler.get_task_keys()
        assert "timetable:TestStudent" in keys
        assert "summary:TestStudent" in keys
        assert len(keys) == len(scheduler._task_statuses)
        await scheduler.stop()


# ---------------------------------------------------------------------------
# _refresh_timetable tests
# ---------------------------------------------------------------------------

class TestRefreshTimetable:
    """Tests for multi-week timetable refresh."""

    @pytest.mark.asyncio
    async def test_fetches_last_current_and_next_week(self, scheduler, mock_student_context):
        """Should cache the previous and next week alongside the current one."""
        current, last, nxt = MagicMock(), MagicMock(), MagicMock()
        calls: list = []

        async def fake_get(target_date=None):
            calls.append(target_date)
            if target_date is None:
                return current
            return last if target_date == get_last_week_range()[0] else nxt

        mock_student_context.timetable_module.get_actual_timetable = AsyncMock(side_effect=fake_get)

        await scheduler._refresh_timetable(mock_student_context)

        assert mock_student_context.timetable is current
        assert mock_student_context.timetable_last is last
        assert mock_student_context.timetable_next is nxt
        assert calls == [None, get_last_week_range()[0], get_next_week_range()[0]]
        assert mock_student_context.timetable_updated is not None

    @pytest.mark.asyncio
    async def test_current_week_survives_failed_extra_weeks(self, scheduler, mock_student_context):
        """A failing past/future week must not break the current one."""
        current = MagicMock()

        async def fake_get(target_date=None):
            if target_date is None:
                return current
            raise RuntimeError("API down")

        mock_student_context.timetable_module.get_actual_timetable = AsyncMock(side_effect=fake_get)

        await scheduler._refresh_timetable(mock_student_context)

        assert mock_student_context.timetable is current
        assert mock_student_context.timetable_last is None
        assert mock_student_context.timetable_next is None

    def test_timetable_for_week_picks_matching_week(self, scheduler, mock_student_context):
        """Summary weeks map to their own cached timetable."""
        mock_student_context.timetable = MagicMock(name="current")
        mock_student_context.timetable_last = MagicMock(name="last")
        mock_student_context.timetable_next = MagicMock(name="next")

        assert scheduler._timetable_for_week(mock_student_context, "last") is mock_student_context.timetable_last
        assert scheduler._timetable_for_week(mock_student_context, "current") is mock_student_context.timetable
        assert scheduler._timetable_for_week(mock_student_context, "next") is mock_student_context.timetable_next

    def test_timetable_for_week_falls_back_to_current(self, scheduler, mock_student_context):
        """Missing week caches fall back to the current timetable."""
        mock_student_context.timetable = MagicMock(name="current")
        mock_student_context.timetable_last = None
        mock_student_context.timetable_next = None

        assert scheduler._timetable_for_week(mock_student_context, "last") is mock_student_context.timetable
        assert scheduler._timetable_for_week(mock_student_context, "next") is mock_student_context.timetable

    @pytest.mark.asyncio
    async def test_summary_uses_week_specific_timetable(self, scheduler, mock_student_context):
        """Each summary week is built from the timetable of that week."""
        scheduler._running = True
        mock_student_context.timetable = MagicMock(name="current")
        mock_student_context.timetable_last = MagicMock(name="last")
        mock_student_context.timetable_next = MagicMock(name="next")
        mock_student_context.marks = MagicMock()
        mock_student_context.gdrive_client = None
        scheduler._manager.gemini.generate_content = AsyncMock(return_value="summary text")
        mock_student_context.summary_module.get_week_messages.return_value = []
        mock_student_context.summary_module.extract_new_marks.return_value = []
        mock_student_context.summary_module.build_prompt_from_template.side_effect = (
            lambda **kwargs: f"prompt-{kwargs['week_type']}"
        )

        await scheduler._refresh_summary(mock_student_context)

        used = {
            c.kwargs["week_type"]: c.kwargs["timetable"]
            for c in mock_student_context.summary_module.build_prompt_from_template.call_args_list
        }
        assert used["last"] is mock_student_context.timetable_last
        assert used["current"] is mock_student_context.timetable
        assert used["next"] is mock_student_context.timetable_next


# ---------------------------------------------------------------------------
# GDrive sync tests
# ---------------------------------------------------------------------------

class TestRefreshGDrive:
    """Tests for _refresh_gdrive school-year scoping."""

    @pytest.fixture
    def gdrive_client(self) -> MagicMock:
        client = MagicMock()
        client.school_year = "2026/2027"
        client.list_week_files = AsyncMock(return_value=[
            ({"id": "f1", "name": "Week 1.docx"}, 1),
            ({"id": "f2", "name": "Week 2.docx"}, 2),
        ])
        client.fetch_report_from_file = AsyncMock(
            side_effect=lambda info, week, year: MagicMock(
                week_number=week, school_year=year,
            ),
        )
        return client

    @pytest.mark.asyncio
    async def test_no_client_is_a_noop(self, scheduler, mock_student_context):
        mock_student_context.gdrive_client = None

        await scheduler._refresh_gdrive(mock_student_context)

        mock_student_context.gdrive_storage.save_report.assert_not_called()

    @pytest.mark.asyncio
    async def test_syncs_new_school_year_over_old_week_numbers(
        self, scheduler, mock_student_context, gdrive_client,
    ):
        """Last year's stored week 1 must not block this year's week 1."""
        mock_student_context.gdrive_client = gdrive_client
        # Storage only has these weeks for the *previous* school year.
        mock_student_context.gdrive_storage.report_exists.side_effect = (
            lambda week, year: year == "2025/2026"
        )

        await scheduler._refresh_gdrive(mock_student_context)

        assert mock_student_context.gdrive_storage.save_report.call_count == 2
        for call in mock_student_context.gdrive_storage.save_report.call_args_list:
            assert call.args[1] == "2026/2027"

    @pytest.mark.asyncio
    async def test_checks_existence_per_school_year(
        self, scheduler, mock_student_context, gdrive_client,
    ):
        mock_student_context.gdrive_client = gdrive_client
        mock_student_context.gdrive_storage.report_exists.return_value = False

        await scheduler._refresh_gdrive(mock_student_context)

        mock_student_context.gdrive_storage.report_exists.assert_any_call(
            1, "2026/2027",
        )

    @pytest.mark.asyncio
    async def test_skips_reports_already_stored_for_this_year(
        self, scheduler, mock_student_context, gdrive_client,
    ):
        mock_student_context.gdrive_client = gdrive_client
        mock_student_context.gdrive_storage.report_exists.side_effect = (
            lambda week, year: week == 1
        )

        await scheduler._refresh_gdrive(mock_student_context)

        assert mock_student_context.gdrive_storage.save_report.call_count == 1
        gdrive_client.fetch_report_from_file.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_one_failed_download_does_not_stop_the_rest(
        self, scheduler, mock_student_context, gdrive_client,
    ):
        mock_student_context.gdrive_client = gdrive_client
        mock_student_context.gdrive_storage.report_exists.return_value = False

        async def flaky(info, week, year):
            if week == 1:
                raise RuntimeError("download failed")
            return MagicMock(week_number=week, school_year=year)

        gdrive_client.fetch_report_from_file = AsyncMock(side_effect=flaky)

        await scheduler._refresh_gdrive(mock_student_context)

        assert mock_student_context.gdrive_storage.save_report.call_count == 1
