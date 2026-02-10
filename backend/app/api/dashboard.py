"""Dashboard aggregated endpoint."""

from datetime import date

from fastapi import APIRouter

from ..dependencies import get_manager, get_student_or_404

router = APIRouter(tags=["dashboard"])


@router.get("/api/students/{name}/dashboard")
async def get_dashboard(name: str):
    """Get all widget data in one call."""
    ctx = get_student_or_404(name)

    # Today's timetable
    today_timetable = None
    if ctx.timetable:
        day = ctx.timetable.get_day(date.today())
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

    # Komens
    komens = None
    if ctx.komens:
        komens = ctx.komens.to_summary_dict()

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
        "komens": komens,
        "marks": marks,
        "prepare_today": prepare_today,
        "prepare_tomorrow": prepare_tomorrow,
    }
