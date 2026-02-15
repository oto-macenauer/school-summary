"""Background task scheduler with status tracking."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Callable, Coroutine

from ..models.config import AppConfig
from ..modules.summary import (
    SummaryData,
    get_current_week_range,
    get_last_week_range,
    get_next_week_range,
)
from ..modules.mail_sync import sync_mail_from_gdrive
from ..modules.prepare import PrepareData, get_tomorrow
from .log_manager import LogCategory, get_log_manager
from .student_manager import StudentContext, StudentManager

_LOGGER = logging.getLogger("bakalari.scheduler")


@dataclass
class TaskStatus:
    """Tracks execution metadata for a scheduled task."""

    task_name: str
    student: str
    interval_seconds: int
    last_run: datetime | None = None
    last_duration_ms: int | None = None
    last_status: str = "pending"
    last_error: str | None = None
    next_run: datetime | None = None
    run_count: int = 0
    error_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_name": self.task_name,
            "student": self.student,
            "interval_seconds": self.interval_seconds,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "last_duration_ms": self.last_duration_ms,
            "last_status": self.last_status,
            "last_error": self.last_error,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "run_count": self.run_count,
            "error_count": self.error_count,
        }


class BackgroundScheduler:
    """Schedules periodic data refresh for all students."""

    def __init__(self, manager: StudentManager, config: AppConfig) -> None:
        self._manager = manager
        self._config = config
        self._tasks: list[asyncio.Task] = []
        self._task_statuses: dict[str, TaskStatus] = {}
        self._running = False

    @property
    def task_statuses(self) -> dict[str, TaskStatus]:
        return self._task_statuses

    def get_task_status(self, task_name: str) -> TaskStatus | None:
        return self._task_statuses.get(task_name)

    async def start(self) -> None:
        """Start all periodic tasks."""
        self._running = True
        intervals = self._config.update_intervals

        for name, ctx in self._manager.students.items():
            self._schedule_task(f"timetable:{name}", intervals.timetable, self._refresh_timetable, ctx)
            self._schedule_task(f"marks:{name}", intervals.marks, self._refresh_marks, ctx)
            self._schedule_task(f"komens:{name}", intervals.komens, self._refresh_komens, ctx)
            self._schedule_task(f"summary:{name}", intervals.summary, self._refresh_summary, ctx)
            self._schedule_task(f"prepare:{name}", intervals.prepare, self._refresh_prepare, ctx)
            if ctx.gdrive_client:
                self._schedule_task(f"gdrive:{name}", intervals.gdrive, self._refresh_gdrive, ctx)
            if ctx.gdrive_client and ctx.mail_folder_id:
                self._schedule_task(f"mail:{name}", intervals.mail, self._refresh_mail, ctx)

        # Canteen is school-wide, schedule once (not per-student)
        if self._manager.canteen_module:
            self._schedule_canteen_task(intervals.canteen)

        _LOGGER.info("Scheduler started with %d tasks", len(self._tasks))

    def _schedule_task(
        self,
        task_key: str,
        interval: int,
        coro_fn: Callable[..., Coroutine],
        ctx: StudentContext,
    ) -> None:
        status = TaskStatus(
            task_name=task_key.split(":")[0],
            student=ctx.name,
            interval_seconds=interval,
            next_run=datetime.now(),
        )
        self._task_statuses[task_key] = status
        task = asyncio.create_task(self._run_periodic(task_key, interval, coro_fn, ctx))
        self._tasks.append(task)

    async def _run_periodic(
        self,
        task_key: str,
        interval: int,
        coro_fn: Callable[..., Coroutine],
        ctx: StudentContext,
    ) -> None:
        status = self._task_statuses[task_key]
        log_mgr = get_log_manager()

        while self._running:
            start = time.monotonic()
            status.last_run = datetime.now()

            try:
                await coro_fn(ctx)
                elapsed = int((time.monotonic() - start) * 1000)
                status.last_duration_ms = elapsed
                status.last_status = "success"
                status.last_error = None
                status.run_count += 1
                log_mgr.log(
                    LogCategory.SCHEDULER, "INFO",
                    f"Task {task_key} completed in {elapsed}ms",
                    student=ctx.name,
                )
            except asyncio.CancelledError:
                return
            except Exception as err:
                elapsed = int((time.monotonic() - start) * 1000)
                status.last_duration_ms = elapsed
                status.last_status = "error"
                status.last_error = str(err)
                status.run_count += 1
                status.error_count += 1
                _LOGGER.error("Task %s failed: %s", task_key, err)
                log_mgr.log(
                    LogCategory.SCHEDULER, "ERROR",
                    f"Task {task_key} failed: {err}",
                    student=ctx.name,
                    details={"error": str(err)},
                )

            status.next_run = datetime.now() + timedelta(seconds=interval)

            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                return

    async def _refresh_timetable(self, ctx: StudentContext) -> None:
        ctx.timetable = await ctx.timetable_module.get_actual_timetable()
        ctx.timetable_updated = datetime.now()
        _LOGGER.debug("Refreshed timetable for %s", ctx.name)

    async def _refresh_marks(self, ctx: StudentContext) -> None:
        ctx.marks = await ctx.marks_module.get_marks()
        ctx.marks_updated = datetime.now()
        _LOGGER.debug("Refreshed marks for %s", ctx.name)

    async def _refresh_komens(self, ctx: StudentContext) -> None:
        try:
            data = await ctx.komens_module.get_all_messages()
            ctx.komens = data
            ctx.komens_updated = datetime.now()
            # Save new messages to storage
            ctx.komens_storage.save_all_messages(data)
            _LOGGER.debug("Refreshed komens for %s", ctx.name)
        except Exception as err:
            if "403" in str(err):
                _LOGGER.debug("Komens not available for %s (403)", ctx.name)
            else:
                raise

    async def _refresh_summary(self, ctx: StudentContext) -> None:
        gemini = self._manager.gemini
        if not gemini:
            return

        if ctx.timetable is None or ctx.marks is None:
            log_mgr = get_log_manager()
            log_mgr.log(
                LogCategory.SCHEDULER, "INFO",
                f"Summary waiting for timetable/marks data for {ctx.name}",
                student=ctx.name,
            )
            ready = await self._wait_for_data(ctx, needs_timetable=True, needs_marks=True)
            if not ready:
                log_mgr.log(
                    LogCategory.SCHEDULER, "WARNING",
                    f"Summary timed out waiting for data for {ctx.name}",
                    student=ctx.name,
                )

        prompts = self._config.prompts

        # Fetch GDrive reports for the relevant weeks
        async def get_gdrive_content(week_start: date, week_end: date) -> str:
            gdrive = ctx.gdrive_client
            if not gdrive:
                return ""
            try:
                from ..core.gdrive import get_school_week_number, get_school_year_start
                school_start = get_school_year_start(week_start)
                week_num = get_school_week_number(week_start, school_start)

                # Check storage first
                stored = ctx.gdrive_storage.get_report(week_num)
                if stored:
                    return stored

                # Fetch from GDrive
                report = await gdrive.get_week_report(week_number=week_num)
                if report:
                    school_year = f"{school_start.year}/{school_start.year + 1}"
                    ctx.gdrive_storage.save_report(report, school_year)
                    return report.content
            except Exception as err:
                _LOGGER.warning("Failed to get GDrive report: %s", err)
            return ""

        for week_type, get_range in [
            ("last", get_last_week_range),
            ("current", get_current_week_range),
            ("next", get_next_week_range),
        ]:
            week_start, week_end = get_range()
            messages = ctx.summary_module.get_week_messages(week_start, week_end)
            marks = ctx.summary_module.extract_new_marks(ctx.marks, week_start, week_end)
            gdrive_content = await get_gdrive_content(week_start, week_end)

            prompt = ctx.summary_module.build_prompt_from_template(
                template=prompts.summary,
                messages=messages,
                timetable=ctx.timetable,
                marks=marks,
                week_start=week_start,
                week_end=week_end,
                week_type=week_type,
                gdrive_report=gdrive_content,
                student_info=ctx.student_info,
            )

            text = await gemini.generate_content(
                prompt=prompt,
                system_instruction=prompts.summary_system,
            )

            summary = SummaryData(
                student_name=ctx.name,
                week_start=week_start,
                week_end=week_end,
                summary_text=text,
                messages_count=len(messages),
                marks_count=len(marks),
                week_type=week_type,
            )

            if week_type == "last":
                ctx.summary_last = summary
            elif week_type == "current":
                ctx.summary_current = summary
            else:
                ctx.summary_next = summary

        ctx.summary_updated = datetime.now()
        _LOGGER.info("Refreshed summaries for %s", ctx.name)

    async def _refresh_prepare(self, ctx: StudentContext) -> None:
        gemini = self._manager.gemini
        if not gemini:
            return

        if ctx.timetable is None:
            log_mgr = get_log_manager()
            log_mgr.log(
                LogCategory.SCHEDULER, "INFO",
                f"Prepare waiting for timetable data for {ctx.name}",
                student=ctx.name,
            )
            ready = await self._wait_for_data(ctx, needs_timetable=True, needs_marks=False)
            if not ready:
                log_mgr.log(
                    LogCategory.SCHEDULER, "WARNING",
                    f"Prepare timed out waiting for data for {ctx.name}",
                    student=ctx.name,
                )

        prompts = self._config.prompts

        for period, target_date, template in [
            ("today", date.today(), prompts.prepare_today),
            ("tomorrow", get_tomorrow(), prompts.prepare_tomorrow),
        ]:
            messages = ctx.prepare_module.get_relevant_messages(target_date)
            prompt = ctx.prepare_module.build_prompt_from_template(
                template=template,
                messages=messages,
                timetable=ctx.timetable,
                target_date=target_date,
                student_info=ctx.student_info,
            )

            text = await gemini.generate_content(
                prompt=prompt,
                system_instruction=prompts.prepare_system,
            )

            _, lessons_count = ctx.prepare_module.format_lessons(ctx.timetable, target_date)

            prep = PrepareData(
                student_name=ctx.name,
                target_date=target_date,
                preparation_text=text,
                lessons_count=lessons_count,
                messages_count=len(messages),
                period=period,
            )

            if period == "today":
                ctx.prepare_today = prep
            else:
                ctx.prepare_tomorrow = prep

        ctx.prepare_updated = datetime.now()
        _LOGGER.info("Refreshed preparation for %s", ctx.name)

    async def _refresh_gdrive(self, ctx: StudentContext) -> None:
        """Sync all available weekly reports from Google Drive."""
        gdrive = ctx.gdrive_client
        if not gdrive:
            return

        import re
        from ..core.gdrive import get_school_year_start

        school_start = get_school_year_start()
        school_year = f"{school_start.year}/{school_start.year + 1}"
        synced = 0

        subfolders = await gdrive.list_folders()
        for folder in subfolders:
            query = f"'{folder.id}' in parents and trashed = false"
            params = {"q": query, "fields": "files(id, name, mimeType)", "pageSize": "50"}
            from ..core.gdrive import GDRIVE_FILES_ENDPOINT
            response = await gdrive._api_request("GET", GDRIVE_FILES_ENDPOINT, params=params)
            if response.status != 200:
                continue
            files = (await response.json()).get("files", [])
            for file_info in files:
                name = file_info.get("name", "")
                # Extract week number from filename like "Week 14.docx"
                match = re.search(r"(\d+)", name)
                if not match:
                    continue
                week_num = int(match.group(1))
                if not gdrive._matches_week_number(name, week_num):
                    continue
                if ctx.gdrive_storage.report_exists(week_num):
                    continue
                try:
                    report = await gdrive.get_week_report(week_number=week_num)
                    if report:
                        ctx.gdrive_storage.save_report(report, school_year)
                        synced += 1
                except Exception as err:
                    _LOGGER.warning("Failed to sync GDrive week %d: %s", week_num, err)

        if synced:
            _LOGGER.info("Synced %d new GDrive reports for %s", synced, ctx.name)

    async def _refresh_mail(self, ctx: StudentContext) -> None:
        """Sync new mail files from Google Drive."""
        gdrive = ctx.gdrive_client
        if not gdrive or not ctx.mail_folder_id:
            return
        await sync_mail_from_gdrive(gdrive, ctx.mail_folder_id, ctx.mail_storage)
        _LOGGER.debug("Refreshed mail for %s", ctx.name)

    def _schedule_canteen_task(self, interval: int) -> None:
        task_key = "canteen:global"
        status = TaskStatus(
            task_name="canteen",
            student="global",
            interval_seconds=interval,
            next_run=datetime.now(),
        )
        self._task_statuses[task_key] = status
        task = asyncio.create_task(self._run_canteen_periodic(task_key, interval))
        self._tasks.append(task)

    async def _run_canteen_periodic(self, task_key: str, interval: int) -> None:
        status = self._task_statuses[task_key]
        log_mgr = get_log_manager()

        while self._running:
            start = time.monotonic()
            status.last_run = datetime.now()

            try:
                await self._refresh_canteen()
                elapsed = int((time.monotonic() - start) * 1000)
                status.last_duration_ms = elapsed
                status.last_status = "success"
                status.last_error = None
                status.run_count += 1
                log_mgr.log(
                    LogCategory.SCHEDULER, "INFO",
                    f"Task {task_key} completed in {elapsed}ms",
                )
            except asyncio.CancelledError:
                return
            except Exception as err:
                elapsed = int((time.monotonic() - start) * 1000)
                status.last_duration_ms = elapsed
                status.last_status = "error"
                status.last_error = str(err)
                status.run_count += 1
                status.error_count += 1
                _LOGGER.error("Task %s failed: %s", task_key, err)
                log_mgr.log(
                    LogCategory.SCHEDULER, "ERROR",
                    f"Task {task_key} failed: {err}",
                    details={"error": str(err)},
                )

            status.next_run = datetime.now() + timedelta(seconds=interval)

            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                return

    async def _refresh_canteen(self) -> None:
        module = self._manager.canteen_module
        if not module:
            return
        self._manager.canteen = await module.get_menu()
        self._manager.canteen_updated = datetime.now()
        _LOGGER.debug("Refreshed canteen menu")

    async def _wait_for_data(
        self,
        ctx: StudentContext,
        needs_timetable: bool = True,
        needs_marks: bool = True,
        poll_interval: float = 5.0,
        timeout: float = 300.0,
    ) -> bool:
        """Wait for required data to be populated on a StudentContext.

        Returns True if all required data became available, False on timeout.
        """
        start = time.monotonic()
        while self._running and (time.monotonic() - start) < timeout:
            timetable_ok = (not needs_timetable) or (ctx.timetable is not None)
            marks_ok = (not needs_marks) or (ctx.marks is not None)
            if timetable_ok and marks_ok:
                return True
            try:
                await asyncio.sleep(poll_interval)
            except asyncio.CancelledError:
                return False
        return False

    async def stop(self) -> None:
        """Cancel all periodic tasks."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        _LOGGER.info("Scheduler stopped")
