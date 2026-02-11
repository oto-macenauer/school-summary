"""Canteen menu endpoints."""

from fastapi import APIRouter

from ..dependencies import get_manager

router = APIRouter(tags=["canteen"])


@router.get("/api/canteen")
async def get_canteen():
    """Get current canteen menu."""
    manager = get_manager()
    if manager.canteen:
        return manager.canteen.to_dict()
    if manager.canteen_module:
        data = await manager.canteen_module.get_menu()
        return data.to_dict()
    return {"days": [], "fetched_at": None}
