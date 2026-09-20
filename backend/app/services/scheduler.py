"""Background task scheduler with status tracking."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Coroutine

from ..models.config import AppConfig
from ..modules.summary import (
    SummaryData,
    get_current_week_range,
    get_last_week_range,
    get_next_week_range,
)
from ..modules.agenda import plural_cs, sort_events, sort_tasks
from ..modules.mail_sync import sync_mail_from_gdrive
from ..modules.prepare import PrepareData, get_tomorrow
from ..modules.tagging import TaggableMessage, TaggingModule
from ..storage.tag_storage import TagStorage
from .log_manager import LogCategory, get_log_manager
from .push_service import PushService
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

    def __init__(
        self,
        manager: StudentManager,
        config: AppConfig,
        push_service: PushService | None = None,
    ) -> None:
        self._manager = manager
        self._config = config
        self._push_service = push_service
        self._tasks: list[asyncio.Task] = []
        self._task_statuses: dict[str, TaskStatus] = {}
        self._task_callables: dict[str, tuple[Callable[..., Coroutine], StudentContext | None]] = {}
        self._running = False
        self._last_prompts: dict[str, str] = {}
        self._known_mark_ids: dict[str, set[str]] = {}

    @property
    def task_statuses(self) -> dict[str, TaskStatus]:
        return self._task_statuses

    def get_task_status(self, task_name: str) -> TaskStatus | None:
        return self._task_statuses.get(task_name)

    def get_task_keys(self) -> list[str]:
        """Return all registered task keys."""
        return list(self._task_statuses.keys())

    async def trigger_task(self, task_key: str) -> bool:
        """Trigger a single task to run immediately. Returns True on success."""
        if task_key not in self._task_callables:
            return False

        coro_fn, ctx = self._task_callables[task_key]
        status = self._task_statuses.get(task_key)
        log_mgr = get_log_manager()

        start = time.monotonic()
        if status:
            status.last_run = datetime.now()

        try:
            if ctx is not None:
                await coro_fn(ctx)
            else:
                await coro_fn()
            elapsed = int((time.monotonic() - start) * 1000)
            if status:
                status.last_duration_ms = elapsed
                status.last_status = "success"
                status.last_error = None
                status.run_count += 1
                status.next_run = datetime.now() + timedelta(seconds=status.interval_seconds)
            log_mgr.log(
                LogCategory.SCHEDULER, "INFO",
                f"Task {task_key} triggered manually, completed in {elapsed}ms",
            )
            return True
        except Exception as err:
            elapsed = int((time.monotonic() - start) * 1000)
            if status:
                status.last_duration_ms = elapsed
                status.last_status = "error"
                status.last_error = str(err)
                status.run_count += 1
                status.error_count += 1
            _LOGGER.error("Manually triggered task %s failed: %s", task_key, err)
            log_mgr.log(
                LogCategory.SCHEDULER, "ERROR",
                f"Task {task_key} triggered manually, failed: {err}",
                details={"error": str(err)},
            )
            raise

    async def start(self) -> None:
        """Start all periodic tasks."""
        self._running = True
        intervals = self._config.update_intervals

        # Load cached AI data from disk before scheduling tasks
        for name, ctx in self._manager.students.items():
            cached = ctx.ai_storage.load_all()
            for key, (data, prompt_hash) in cached.items():
                if key.startswith("summary:"):
                    week_type = key.split(":")[1]
                    setattr(ctx, f"summary_{week_type}", data)
                    if prompt_hash:
                        self._last_prompts[f"summary:{ctx.name}:{week_type}"] = prompt_hash
                elif key.startswith("prepare:"):
                    period = key.split(":")[1]
                    setattr(ctx, f"prepare_{period}", data)
                    if prompt_hash:
                        self._last_prompts[f"prepare:{ctx.name}:{period}"] = prompt_hash
            if cached:
                _LOGGER.info("Loaded %d cached AI results for %s", len(cached), name)

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
            if self._manager.gemini:
                self._schedule_task(f"tagging:{name}", intervals.tagging, self._refresh_tags, ctx)
            if self._push_service:
                self._schedule_task(
                    f"agenda_digest:{name}",
                    intervals.agenda_digest,
                    self._agenda_digest,
                    ctx,
                )

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
        self._task_callables[task_key] = (coro_fn, ctx)
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
        """Refresh last, current and next week timetables.

        Past weeks carry the notes teachers recorded (what was taught), which
        feed the weekly summaries, so they are fetched alongside the current one.
        """
        ctx.timetable = await ctx.timetable_module.get_actual_timetable()

        last_start, _ = get_last_week_range()
        next_start, _ = get_next_week_range()
        for attr, week_start in (("timetable_last", last_start), ("timetable_next", next_start)):
            try:
                setattr(
                    ctx, attr,
                    await ctx.timetable_module.get_actual_timetable(week_start),
                )
            except Exception as err:
                _LOGGER.warning(
                    "Failed to refresh %s for %s: %s", attr, ctx.name, err,
                )

        ctx.timetable_updated = datetime.now()
        _LOGGER.debug("Refreshed timetables for %s", ctx.name)

    @staticmethod
    def _timetable_for_week(ctx: StudentContext, week_type: str):
        """Return the cached timetable matching the summary week."""
        if week_type == "last":
            return ctx.timetable_last or ctx.timetable
        if week_type == "next":
            return ctx.timetable_next or ctx.timetable
        return ctx.timetable

    async def _refresh_marks(self, ctx: StudentContext) -> None:
        old_mark_ids = self._known_mark_ids.get(ctx.name, set())
        new_data = await ctx.marks_module.get_marks()

        # Collect all mark IDs from the new data
        current_ids: set[str] = set()
        new_marks_info: list[tuple[str, str]] = []  # (subject, mark_text)
        for subject in new_data.subjects:
            for mark in subject.marks:
                current_ids.add(mark.mark_id)
                if old_mark_ids and mark.mark_id not in old_mark_ids:
                    new_marks_info.append((subject.subject_name, mark.mark_text))

        self._known_mark_ids[ctx.name] = current_ids
        ctx.marks = new_data
        ctx.marks_updated = datetime.now()
        _LOGGER.debug("Refreshed marks for %s", ctx.name)

        # Send push notification for new marks
        if new_marks_info and self._push_service:
            if len(new_marks_info) == 1:
                subj, grade = new_marks_info[0]
                body = f"{subj}: {grade}"
            else:
                body = f"{len(new_marks_info)} nových známek"
            slug = ctx.name.lower()
            asyncio.create_task(
                self._push_service.send_notification(
                    student=ctx.name,
                    title="Nová známka",
                    body=body,
                    url=f"/{slug}/marks",
                    tag="marks",
                )
            )

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
                from ..core.gdrive import get_school_week_number, school_year_label
                school_start = gdrive.school_year_start_for(week_start)
                week_num = get_school_week_number(week_start, school_start)
                school_year = school_year_label(school_start)

                # Check storage first
                stored = ctx.gdrive_storage.get_report(week_num, school_year)
                if stored:
                    return stored

                # The Drive folder only holds the current school year, so a
                # week on the far side of the September rollover is never
                # fetched — only what is already stored counts.
                if school_year != gdrive.school_year:
                    return ""

                report = await gdrive.get_week_report(
                    week_number=week_num, school_year=school_year,
                )
                if report:
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
            week_timetable = self._timetable_for_week(ctx, week_type)

            prompt = ctx.summary_module.build_prompt_from_template(
                template=prompts.summary,
                messages=messages,
                timetable=week_timetable,
                marks=marks,
                week_start=week_start,
                week_end=week_end,
                week_type=week_type,
                gdrive_report=gdrive_content,
                student_info=ctx.student_info,
            )

            cache_key = f"summary:{ctx.name}:{week_type}"
            prompt_fingerprint = prompt + "\0" + (prompts.summary_system or "")
            prompt_hash = hashlib.sha256(prompt_fingerprint.encode()).hexdigest()

            if self._last_prompts.get(cache_key) == prompt_hash:
                _LOGGER.debug(
                    "Skipping summary %s for %s (prompt unchanged)", week_type, ctx.name,
                )
                continue

            text = await gemini.generate_content(
                prompt=prompt,
                system_instruction=prompts.summary_system,
            )
            self._last_prompts[cache_key] = prompt_hash

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

            ctx.ai_storage.save_summary(summary, prompt_hash)

        ctx.summary_updated = datetime.now()
        _LOGGER.info("Refreshed summaries for %s", ctx.name)

        # Notify about summary update
        if self._push_service:
            slug = ctx.name.lower()
            asyncio.create_task(
                self._push_service.send_notification(
                    student=ctx.name,
                    title="Shrnutí aktualizováno",
                    body="Týdenní shrnutí bylo aktualizováno",
                    url=f"/{slug}",
                    tag="summary",
                )
            )

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

            cache_key = f"prepare:{ctx.name}:{period}"
            prompt_fingerprint = prompt + "\0" + (prompts.prepare_system or "")
            prompt_hash = hashlib.sha256(prompt_fingerprint.encode()).hexdigest()

            if self._last_prompts.get(cache_key) == prompt_hash:
                _LOGGER.debug(
                    "Skipping prepare %s for %s (prompt unchanged)", period, ctx.name,
                )
                continue

            text = await gemini.generate_content(
                prompt=prompt,
                system_instruction=prompts.prepare_system,
            )
            self._last_prompts[cache_key] = prompt_hash

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

            ctx.ai_storage.save_prepare(prep, prompt_hash)

        ctx.prepare_updated = datetime.now()
        _LOGGER.info("Refreshed preparation for %s", ctx.name)

    async def _refresh_gdrive(self, ctx: StudentContext) -> None:
        """Sync all available weekly reports from Google Drive.

        The reports folder holds one school year, so reports are stored under
        the school year in progress.  Week numbers restart every September and
        would otherwise collide with the previous year's stored reports.
        """
        gdrive = ctx.gdrive_client
        if not gdrive:
            return

        school_year = gdrive.school_year
        synced = 0

        for file_info, week_num in await gdrive.list_week_files():
            if ctx.gdrive_storage.report_exists(week_num, school_year):
                continue
            try:
                report = await gdrive.fetch_report_from_file(
                    file_info, week_num, school_year,
                )
                ctx.gdrive_storage.save_report(report, school_year)
                synced += 1
            except Exception as err:
                _LOGGER.warning("Failed to sync GDrive week %d: %s", week_num, err)

        if synced:
            _LOGGER.info(
                "Synced %d new GDrive reports (%s) for %s",
                synced, school_year, ctx.name,
            )

    async def _refresh_mail(self, ctx: StudentContext) -> None:
        """Sync new mail files from Google Drive."""
        gdrive = ctx.gdrive_client
        if not gdrive or not ctx.mail_folder_id:
            return
        await sync_mail_from_gdrive(gdrive, ctx.mail_folder_id, ctx.mail_storage)
        _LOGGER.debug("Refreshed mail for %s", ctx.name)

    async def _refresh_tags(self, ctx: StudentContext) -> None:
        """Extract tags, calendar events and tasks from stored messages."""
        gemini = self._manager.gemini
        if not gemini:
            return

        prompts = self._config.prompts
        tagger = TaggingModule(
            gemini,
            prompt_template=prompts.tagging,
            system_instruction=prompts.tagging_system,
        )

        # Messages tagged by an older schema are re-processed only inside the
        # backfill window — older history is not worth the quota.
        backfill_days = self._config.agenda.backfill_days
        cutoff = date.today() - timedelta(days=backfill_days) if backfill_days else None

        candidates: list[tuple[Path, str]] = []
        for path in ctx.komens_storage.get_saved_files():
            candidates.append((path, "komens"))
        for path in ctx.mail_storage.get_saved_files():
            candidates.append((path, "mail"))
        for path in ctx.gdrive_storage.get_all_reports():
            candidates.append((path, "report"))

        if not candidates:
            return

        taggable: list[TaggableMessage] = []
        path_map: dict[str, Path] = {}

        for path, source_type in candidates:
            msg = self._parse_taggable_from_file(path, source_type)
            if not msg:
                continue
            if not TagStorage.needs_extraction(path, msg.sent_date, cutoff):
                continue
            taggable.append(msg)
            path_map[msg.message_id] = path

        if not taggable:
            return

        # Tag most recent messages first
        taggable.sort(key=lambda m: m.sent_date or date.min, reverse=True)
        source_map = {m.message_id: m.source_id for m in taggable}

        results = await tagger.tag_messages(taggable)

        written = 0
        events_found = 0
        tasks_found = 0
        for msg_id, extraction in results.items():
            path = path_map.get(msg_id)
            if not path:
                continue
            TagStorage.write_tags(path, extraction.tags)
            written += 1
            source = source_map.get(msg_id)
            if source:
                # Replaces exactly this message's records; user state survives.
                ctx.agenda_storage.replace_source(
                    source, extraction.events, extraction.tasks,
                )
                events_found += len(extraction.events)
                tasks_found += len(extraction.tasks)

        if written:
            _LOGGER.info(
                "Tagged %d messages for %s (%d events, %d tasks)",
                written, ctx.name, events_found, tasks_found,
            )
            get_log_manager().log(
                LogCategory.SCHEDULER, "INFO",
                f"Tagged {written} messages for {ctx.name}",
                student=ctx.name,
                details={"events": events_found, "tasks": tasks_found},
            )

    async def _agenda_digest(self, ctx: StudentContext) -> None:
        """Push one digest a day: tomorrow's events and tasks coming due."""
        agenda_cfg = self._config.agenda
        if not agenda_cfg.reminder_enabled or not self._push_service:
            return

        now = datetime.now()
        if now.hour < agenda_cfg.reminder_hour:
            return

        today = now.date()
        storage = ctx.agenda_storage
        if storage.last_digest_date() == today:
            return

        tomorrow = today + timedelta(days=1)
        state = storage.load_state()

        def _active(item_id: str) -> bool:
            entry = state.get(item_id)
            return not (entry and (entry.done or entry.dismissed))

        events = sort_events([
            e for e in storage.load_events()
            if _active(e.id) and e.date_from <= tomorrow <= e.date_end
        ])
        task_cutoff = today + timedelta(days=agenda_cfg.reminder_task_days)
        tasks = sort_tasks([
            t for t in storage.load_tasks()
            if _active(t.id) and t.due is not None and t.due <= task_cutoff
        ])

        if not events and not tasks:
            # Nothing to say — remember the day anyway so the check stays cheap.
            storage.set_last_digest_date(today)
            return

        parts: list[str] = []
        if events:
            parts.append("Zítra: " + ", ".join(e.title for e in events[:3]))
        if tasks:
            parts.append("Nezapomeň: " + ", ".join(t.title for t in tasks[:3]))
        body = " · ".join(parts)
        extra = len(events[3:]) + len(tasks[3:])
        if extra:
            body += f" (+{extra} {plural_cs(extra, 'další', 'další', 'dalších')})"

        await self._push_service.send_notification(
            ctx.name,
            title=f"{ctx.name} — zítřek",
            body=body,
            url=f"/{ctx.name.lower()}/calendar",
            tag="agenda",
        )
        storage.set_last_digest_date(today)
        _LOGGER.info(
            "Sent agenda digest for %s (%d events, %d tasks)",
            ctx.name, len(events), len(tasks),
        )

    @staticmethod
    def _parse_taggable_from_file(
        path: Path, source_type: str,
    ) -> TaggableMessage | None:
        """Parse a markdown file into a TaggableMessage."""
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            return None

        fm = TagStorage.parse_frontmatter(content)

        # Extract ID. Reports use report_id because a bare week number repeats
        # every school year and would merge two reports into one source.
        msg_id = (
            fm.get("message_id")
            or fm.get("file_id")
            or fm.get("report_id")
            or fm.get("week_number")
            or path.stem
        )

        # Extract title
        title = fm.get("title") or fm.get("subject") or path.stem

        # Extract date
        sent_date: date | None = None
        date_str = fm.get("date") or fm.get("fetched_at") or ""
        if date_str:
            try:
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                sent_date = dt.date()
            except ValueError:
                pass

        # Extract body (content after frontmatter)
        parts = content.split("---", 2)
        body = parts[2].strip() if len(parts) >= 3 else content.strip()

        return TaggableMessage(
            message_id=msg_id,
            title=title,
            body=body,
            sent_date=sent_date,
            source_type=source_type,
        )

    def _schedule_canteen_task(self, interval: int) -> None:
        task_key = "canteen:global"
        status = TaskStatus(
            task_name="canteen",
            student="global",
            interval_seconds=interval,
            next_run=datetime.now(),
        )
        self._task_statuses[task_key] = status
        self._task_callables[task_key] = (self._refresh_canteen_wrapper, None)
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

    async def _refresh_canteen_wrapper(self) -> None:
        """No-arg wrapper so canteen can be triggered via trigger_task."""
        await self._refresh_canteen()

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
