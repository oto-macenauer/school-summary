"""Mail (Gmail sync) endpoints."""

from fastapi import APIRouter

from ..dependencies import get_student_or_404

router = APIRouter(tags=["mail"])


@router.get("/api/students/{name}/mail")
async def get_mail(name: str):
    """Get all synced mail messages for a student."""
    ctx = get_student_or_404(name)
    data = ctx.mail_storage.load_all_messages()
    return data.to_summary_dict()
