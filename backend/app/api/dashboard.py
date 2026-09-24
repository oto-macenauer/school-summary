"""Dashboard aggregated endpoint."""

import re
from datetime import date

from fastapi import APIRouter

from ..dependencies import get_manager, get_student_or_404
from ..modules.agenda import ItemState, upcoming_events
from .agenda import open_task_counts, task_dicts, with_state
from .resources import collect_resources

router = APIRouter(tags=["dashboard"])

RECENT_RESOURCES = 5
PREVIEW_CHARS = 160


def _preview(body: str, is_markdown: bool | None) -> str:
    """Short plain-text preview of a resource body."""
    text = body
    if is_markdown:
        # Reports are markdown: drop heading/list/emphasis markers
        text = re.sub(r"^\s*(#+|[-*]|\d+\.)\s+", "", text, flags=re.MULTILINE)
        text = text.replace("**", "").replace("__", "")
    text = " ".join(text.split())
    if len(text) <= PREVIEW_CHARS:
        return text
    return text[:PREVIEW_CHARS].rstrip() + "…"


@router.get("/api/students/{name}/dashboard")
async def get_dashboard(name: str):
    """Get all widget data in one call."""
    ctx = get_student_or_404(name)

    # Closest school day timetable
    today_timetable = None
    if ctx.timetable:
        day = ctx.timetable.get_closest_school_day(date.today())
        if day:
            today_timetable = day.to_detailed_dict()

    # Weekly summaries (last, current, next)
    def _fmt_summary(s):
        if not s:
            return None
        return {"summary_text": s.summary_text, **s.to_dict()}

    summary_last = _fmt_summary(ctx.summary_last)
    summary_current = _fmt_summary(ctx.summary_current)
    summary_next = _fmt_summary(ctx.summary_next)

    # Latest messages of every kind (komens, mail, reports)
    all_resources = collect_resources(ctx)
    resources = {
        "recent": [
            {
                **{k: v for k, v in item.items() if k != "body"},
                "preview": _preview(item.get("body") or "", item.get("isMarkdown")),
            }
            for item in all_resources[:RECENT_RESOURCES]
        ],
        "total": len(all_resources),
        "unread_count": sum(
            1 for i in all_resources
            if i["category"] == "komens" and i.get("isRead") is False
        ),
    }

    # Marks
    marks = None
    if ctx.marks:
        marks = ctx.marks.to_summary_dict()

    # Prepare today
    prepare_today = None
    if ctx.prepare_today:
        prepare_today = {
            "preparation_text": ctx.prepare_today.preparation_text,
            **ctx.prepare_today.to_dict(),
        }

    # Prepare tomorrow
    prepare_tomorrow = None
    if ctx.prepare_tomorrow:
        prepare_tomorrow = {
            "preparation_text": ctx.prepare_tomorrow.preparation_text,
            **ctx.prepare_tomorrow.to_dict(),
        }

    # Agenda: the next few calendar entries and the open checklist
    today = date.today()
    states = ctx.agenda_storage.load_state()
    all_events = ctx.agenda_storage.load_events()
    all_tasks = ctx.agenda_storage.load_tasks()

    agenda_events = [
        with_state(e.to_dict(), states.get(e.id, ItemState()))
        for e in upcoming_events(all_events, today, 30)
        if not states.get(e.id, ItemState()).dismissed
    ][:5]
    open_tasks = task_dicts(
        all_tasks, states, include_done=False, include_dismissed=False,
    )

    # Extra subjects from config
    extra_subjects = []
    manager = get_manager()
    if manager.config:
        student_cfg = next(
            (s for s in manager.config.students if s.name == name), None
        )
        if student_cfg:
            extra_subjects = [e.model_dump() for e in student_cfg.extra_subjects]

    return {
        "student": name,
        "today_timetable": today_timetable,
        "extra_subjects": extra_subjects,
        "summary_last": summary_last,
        "summary_current": summary_current,
        "summary_next": summary_next,
        "resources": resources,
        "marks": marks,
        "prepare_today": prepare_today,
        "prepare_tomorrow": prepare_tomorrow,
        "agenda_events": agenda_events,
        "agenda_tasks": open_tasks[:6],
        "agenda_task_counts": open_task_counts(all_tasks, states, today),
    }
