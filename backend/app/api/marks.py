"""Marks endpoints."""

from fastapi import APIRouter

from ..dependencies import get_student_or_404

router = APIRouter(tags=["marks"])


@router.get("/api/students/{name}/marks")
async def get_marks(name: str):
    """Get all marks with averages."""
    ctx = get_student_or_404(name)
    if ctx.marks:
        return ctx.marks.to_summary_dict()
    data = await ctx.marks_module.get_marks()
    return data.to_summary_dict()


@router.get("/api/students/{name}/marks/new")
async def get_new_marks(name: str):
    """Get new/unread marks count."""
    ctx = get_student_or_404(name)
    count = await ctx.marks_module.get_new_marks_count()
    return {"count": count}
