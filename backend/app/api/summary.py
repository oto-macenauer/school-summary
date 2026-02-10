"""AI summary endpoints."""

from fastapi import APIRouter, Query

from ..dependencies import get_student_or_404

router = APIRouter(tags=["summary"])


@router.get("/api/students/{name}/summary")
async def get_summary(name: str, period: str = Query("current")):
    """Get weekly summary (last/current/next)."""
    ctx = get_student_or_404(name)
    summary_map = {
        "last": ctx.summary_last,
        "current": ctx.summary_current,
        "next": ctx.summary_next,
    }
    summary = summary_map.get(period)
    if summary is None:
        return {
            "summary_text": "Shrnut\u00ed zat\u00edm nen\u00ed k dispozici.",
            "week_type": period,
            **({} if not summary else summary.to_dict()),
        }
    return {
        "summary_text": summary.summary_text,
        **summary.to_dict(),
    }
