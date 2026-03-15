"""Web Push notification service with VAPID key management."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from pywebpush import WebPushException, webpush

from ..config import get_app_data_dir

_LOGGER = logging.getLogger("bakalari.push")

_VAPID_KEYS_FILE = "vapid_keys.json"
_SUBSCRIPTIONS_FILE = "push_subscriptions.json"


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _generate_vapid_keys() -> dict[str, str]:
    """Generate a new VAPID key pair."""
    private_key = ec.generate_private_key(ec.SECP256R1())

    # Private key as PEM (needed by pywebpush)
    pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")

    # Public key as base64url uncompressed point (needed by browser)
    public_bytes = private_key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )

    return {
        "private_key_pem": pem,
        "public_key": _base64url_encode(public_bytes),
    }


class PushService:
    """Manages Web Push subscriptions and sends notifications."""

    def __init__(self) -> None:
        self._private_key_pem: str = ""
        self._public_key: str = ""
        self._subscriptions: dict[str, list[dict[str, Any]]] = {}
        self._app_data: Path = get_app_data_dir()

    @property
    def public_key(self) -> str:
        return self._public_key

    @property
    def available(self) -> bool:
        return bool(self._private_key_pem and self._public_key)

    def initialize(self) -> None:
        """Load or generate VAPID keys and load existing subscriptions."""
        self._app_data.mkdir(parents=True, exist_ok=True)

        # Load or generate VAPID keys
        keys_path = self._app_data / _VAPID_KEYS_FILE
        if keys_path.exists():
            keys = json.loads(keys_path.read_text(encoding="utf-8"))
            self._private_key_pem = keys["private_key_pem"]
            self._public_key = keys["public_key"]
            _LOGGER.info("Loaded VAPID keys")
        else:
            keys = _generate_vapid_keys()
            keys_path.write_text(json.dumps(keys, indent=2), encoding="utf-8")
            self._private_key_pem = keys["private_key_pem"]
            self._public_key = keys["public_key"]
            _LOGGER.info("Generated new VAPID keys")

        # Load existing subscriptions
        subs_path = self._app_data / _SUBSCRIPTIONS_FILE
        if subs_path.exists():
            self._subscriptions = json.loads(subs_path.read_text(encoding="utf-8"))
            total = sum(len(v) for v in self._subscriptions.values())
            _LOGGER.info("Loaded %d push subscriptions", total)

    def add_subscription(self, student: str, subscription: dict[str, Any]) -> None:
        """Register a push subscription for a student."""
        if student not in self._subscriptions:
            self._subscriptions[student] = []

        endpoint = subscription.get("endpoint", "")
        # Replace if same endpoint exists
        self._subscriptions[student] = [
            s for s in self._subscriptions[student] if s.get("endpoint") != endpoint
        ]
        self._subscriptions[student].append(subscription)
        self._save_subscriptions()
        _LOGGER.info("Added push subscription for %s", student)

    def remove_subscription(self, student: str, endpoint: str) -> None:
        """Remove a push subscription by endpoint."""
        if student in self._subscriptions:
            self._subscriptions[student] = [
                s for s in self._subscriptions[student] if s.get("endpoint") != endpoint
            ]
            if not self._subscriptions[student]:
                del self._subscriptions[student]
            self._save_subscriptions()
            _LOGGER.info("Removed push subscription for %s", student)

    async def send_notification(
        self,
        student: str,
        title: str,
        body: str,
        url: str = "/",
        tag: str = "default",
    ) -> int:
        """Send a push notification to all subscriptions for a student.

        Returns the number of successfully sent notifications.
        """
        if not self.available:
            return 0

        subscriptions = self._subscriptions.get(student, [])
        if not subscriptions:
            return 0

        payload = json.dumps({
            "title": title,
            "body": body,
            "url": url,
            "tag": tag,
        })

        sent = 0
        expired: list[str] = []

        for sub in subscriptions:
            try:
                await asyncio.to_thread(
                    webpush,
                    subscription_info=sub,
                    data=payload,
                    vapid_private_key=self._private_key_pem,
                    vapid_claims={"sub": "mailto:noreply@skolni-prehled.local"},
                )
                sent += 1
            except WebPushException as err:
                status = getattr(err.response, "status_code", None)
                if status in (404, 410):
                    expired.append(sub.get("endpoint", ""))
                    _LOGGER.debug("Subscription expired: %s", sub.get("endpoint", "")[:50])
                else:
                    _LOGGER.warning("Push failed for %s: %s", student, err)
            except Exception as err:
                _LOGGER.warning("Push error for %s: %s", student, err)

        # Clean up expired subscriptions
        if expired:
            self._subscriptions[student] = [
                s for s in self._subscriptions.get(student, [])
                if s.get("endpoint") not in expired
            ]
            self._save_subscriptions()

        if sent:
            _LOGGER.info("Sent %d push notifications for %s", sent, student)
        return sent

    async def broadcast_notification(
        self,
        title: str,
        body: str,
        url: str = "/",
        tag: str = "default",
    ) -> int:
        """Send a notification to all subscriptions across all students."""
        total = 0
        for student in list(self._subscriptions.keys()):
            total += await self.send_notification(student, title, body, url, tag)
        return total

    def _save_subscriptions(self) -> None:
        subs_path = self._app_data / _SUBSCRIPTIONS_FILE
        subs_path.write_text(
            json.dumps(self._subscriptions, indent=2), encoding="utf-8"
        )
