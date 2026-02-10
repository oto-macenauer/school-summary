"""Timetable endpoints."""

from datetime import date

from fastapi import APIRouter, Query

from ..dependencies import get_student_or_404

router = APIRouter(tags=["timetable"])


@router.get("/api/students/{name}/timetable")
async def get_timetable(name: str, date: date | None = Query(None)):
    """Get current or specific week timetable."""
    ctx = get_student_or_404(name)
    if date:
        timetable = await ctx.timetable_module.get_actual_timetable(date)
        return timetable.to_summary_dict()
    if ctx.timetable:
        return ctx.timetable.to_summary_dict()
    timetable = await ctx.timetable_module.get_actual_timetable()
    return timetable.to_summary_dict()
