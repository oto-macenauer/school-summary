"""Tests for BackgroundScheduler service."""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.config import AppConfig, UpdateIntervalsConfig
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
    ctx.marks = None
    ctx.komens = None
    ctx.timetable_module = AsyncMock()
    ctx.marks_module = AsyncMock()
    ctx.komens_module = AsyncMock()
    ctx.summary_module = MagicMock()
    ctx.prepare_module = MagicMock()
    ctx.komens_storage = MagicMock()
    ctx.gdrive_storage = MagicMock()
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
# Scheduler lifecycle tests
# ---------------------------------------------------------------------------

class TestSchedulerLifecycle:
    """Tests for scheduler start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_creates_tasks(self, scheduler):
        """Starting the scheduler should create async tasks."""
        await scheduler.start()
        # 5 tasks per student (timetable, marks, komens, summary, prepare)
        assert len(scheduler._tasks) == 5
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
        assert set(scheduler._task_statuses.keys()) == expected_keys
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
