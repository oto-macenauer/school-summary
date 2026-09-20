"""Calendar and checklist endpoints backed by the extracted agenda records."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..dependencies import get_manager, get_student_or_404
from ..modules.agenda import (
    AgendaEvent,
    AgendaTask,
    ItemState,
    filter_events_window,
    sort_events,
    sort_tasks,
)
from ..services.student_manager import StudentContext

router = APIRouter(tags=["agenda"])


class ItemStateRequest(BaseModel):
    """Partial update — omitted fields are left as they are."""

    done: bool | None = None
    dismissed: bool | None = None


def _agenda_config():
    manager = get_manager()
    if manager.config:
        return manager.config.agenda
    from ..models.config import AgendaConfig

    return AgendaConfig()


def with_state(item: dict[str, Any], state: ItemState) -> dict[str, Any]:
    item["done"] = state.done
    item["done_at"] = state.done_at.isoformat() if state.done_at else None
    item["dismissed"] = state.dismissed
    return item


def event_dicts(
    events: list[AgendaEvent],
    states: dict[str, ItemState],
    include_dismissed: bool,
) -> list[dict[str, Any]]:
    result = []
    for event in sort_events(events):
        state = states.get(event.id, ItemState())
        if state.dismissed and not include_dismissed:
            continue
        result.append(with_state(event.to_dict(), state))
    return result


def task_dicts(
    tasks: list[AgendaTask],
    states: dict[str, ItemState],
    include_done: bool,
    include_dismissed: bool,
) -> list[dict[str, Any]]:
    result = []
    for task in sort_tasks(tasks):
        state = states.get(task.id, ItemState())
        if state.dismissed and not include_dismissed:
            continue
        if state.done and not include_done:
            continue
        result.append(with_state(task.to_dict(), state))
    return result


def open_task_counts(
    tasks: list[AgendaTask], states: dict[str, ItemState], today: date,
) -> dict[str, int]:
    """Counts for the dashboard badge: what is still waiting on somebody."""
    open_count = 0
    overdue = 0
    due_soon = 0
    soon = today + timedelta(days=7)
    for task in tasks:
        state = states.get(task.id, ItemState())
        if state.done or state.dismissed:
            continue
        open_count += 1
        if task.due is None:
            continue
        if task.due < today:
            overdue += 1
        elif task.due <= soon:
            due_soon += 1
    return {"open": open_count, "overdue": overdue, "due_soon": due_soon}


def _item_exists(ctx: StudentContext, item_id: str) -> bool:
    if any(e.id == item_id for e in ctx.agenda_storage.load_events()):
        return True
    return any(t.id == item_id for t in ctx.agenda_storage.load_tasks())


@router.get("/api/students/{name}/agenda/events")
async def get_agenda_events(
    name: str,
    past_days: int | None = Query(None, ge=0, le=3650),
    future_days: int | None = Query(None, ge=0, le=3650),
    all_time: bool = Query(False, description="Ignore the rolling window"),
    include_dismissed: bool = False,
):
    """Calendar entries, oldest first, within a rolling window around today."""
    ctx = get_student_or_404(name)
    cfg = _agenda_config()
    today = date.today()

    events = ctx.agenda_storage.load_events()
    if not all_time:
        events = filter_events_window(
            events,
            today,
            past_days if past_days is not None else cfg.past_window_days,
            future_days if future_days is not None else cfg.future_window_days,
        )
    states = ctx.agenda_storage.load_state()

    return {
        "events": event_dicts(events, states, include_dismissed),
        "today": today.isoformat(),
        "window": {
            "past_days": past_days if past_days is not None else cfg.past_window_days,
            "future_days": (
                future_days if future_days is not None else cfg.future_window_days
            ),
            "all_time": all_time,
        },
        "total": len(ctx.agenda_storage.load_events()),
    }


@router.get("/api/students/{name}/agenda/tasks")
async def get_agenda_tasks(
    name: str,
    include_done: bool = True,
    include_dismissed: bool = False,
):
    """Checklist entries: due first, undated last."""
    ctx = get_student_or_404(name)
    today = date.today()

    tasks = ctx.agenda_storage.load_tasks()
    states = ctx.agenda_storage.load_state()

    return {
        "tasks": task_dicts(tasks, states, include_done, include_dismissed),
        "today": today.isoformat(),
        "counts": open_task_counts(tasks, states, today),
    }


@router.post("/api/students/{name}/agenda/items/{item_id}/state")
async def set_item_state(name: str, item_id: str, req: ItemStateRequest):
    """Tick a task off or hide a record the AI got wrong."""
    ctx = get_student_or_404(name)

    if req.done is None and req.dismissed is None:
        raise HTTPException(status_code=400, detail="Nothing to update")
    if not _item_exists(ctx, item_id):
        raise HTTPException(status_code=404, detail=f"Item '{item_id}' not found")

    state = ctx.agenda_storage.set_state(
        item_id, done=req.done, dismissed=req.dismissed,
    )
    return {"id": item_id, **state.to_dict()}
