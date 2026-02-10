"""Komens endpoints."""

from fastapi import APIRouter

from ..dependencies import get_student_or_404

router = APIRouter(tags=["komens"])


@router.get("/api/students/{name}/komens")
async def get_komens(name: str):
    """Get all messages."""
    ctx = get_student_or_404(name)
    if ctx.komens:
        return ctx.komens.to_summary_dict()
    data = await ctx.komens_module.get_all_messages()
    return data.to_summary_dict()


@router.get("/api/students/{name}/komens/unread")
async def get_unread_count(name: str):
    """Get unread message count."""
    ctx = get_student_or_404(name)
    if ctx.komens:
        return {"count": ctx.komens.unread_count}
    count = await ctx.komens_module.get_unread_count()
    return {"count": count}
