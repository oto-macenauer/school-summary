"""Push notification subscription endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..dependencies import get_push_service

router = APIRouter(tags=["notifications"])


class SubscribeRequest(BaseModel):
    student: str
    subscription: dict


class UnsubscribeRequest(BaseModel):
    student: str
    endpoint: str


@router.get("/api/notifications/vapid-key")
async def get_vapid_key():
    """Return the VAPID public key for push subscription."""
    push = get_push_service()
    if not push.available:
        raise HTTPException(status_code=503, detail="Push notifications not available")
    return {"public_key": push.public_key}


@router.post("/api/notifications/subscribe")
async def subscribe(req: SubscribeRequest):
    """Register a push subscription for a student."""
    push = get_push_service()
    if not push.available:
        raise HTTPException(status_code=503, detail="Push notifications not available")
    push.add_subscription(req.student, req.subscription)
    return {"status": "subscribed"}


@router.post("/api/notifications/unsubscribe")
async def unsubscribe(req: UnsubscribeRequest):
    """Remove a push subscription."""
    push = get_push_service()
    if not push.available:
        raise HTTPException(status_code=503, detail="Push notifications not available")
    push.remove_subscription(req.student, req.endpoint)
    return {"status": "unsubscribed"}
