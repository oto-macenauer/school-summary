"""Preparation endpoints."""

from fastapi import APIRouter

from ..dependencies import get_student_or_404

router = APIRouter(tags=["prepare"])


@router.get("/api/students/{name}/prepare/today")
async def get_prepare_today(name: str):
    """Get today's preparation."""
    ctx = get_student_or_404(name)
    if ctx.prepare_today:
        return {
            "preparation_text": ctx.prepare_today.preparation_text,
            **ctx.prepare_today.to_dict(),
        }
    return {"preparation_text": "P\u0159\u00edprava na dne\u0161ek zat\u00edm nen\u00ed k dispozici.", "period": "today"}


@router.get("/api/students/{name}/prepare/tomorrow")
async def get_prepare_tomorrow(name: str):
    """Get tomorrow's preparation."""
    ctx = get_student_or_404(name)
    if ctx.prepare_tomorrow:
        return {
            "preparation_text": ctx.prepare_tomorrow.preparation_text,
            **ctx.prepare_tomorrow.to_dict(),
        }
    return {"preparation_text": "P\u0159\u00edprava na z\u00edt\u0159ek zat\u00edm nen\u00ed k dispozici.", "period": "tomorrow"}
