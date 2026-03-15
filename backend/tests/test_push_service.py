"""Tests for the push notification service."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.push_service import PushService, _generate_vapid_keys


class TestVapidKeyGeneration:
    """Tests for VAPID key generation."""

    def test_generate_vapid_keys_returns_required_fields(self):
        keys = _generate_vapid_keys()
        assert "private_key_pem" in keys
        assert "public_key" in keys

    def test_generate_vapid_keys_private_key_is_pem(self):
        keys = _generate_vapid_keys()
        assert keys["private_key_pem"].startswith("-----BEGIN PRIVATE KEY-----")

    def test_generate_vapid_keys_public_key_is_base64url(self):
        keys = _generate_vapid_keys()
        # Base64url should not contain +, /, or =
        assert "+" not in keys["public_key"]
        assert "/" not in keys["public_key"]
        assert "=" not in keys["public_key"]
        # Uncompressed EC point (65 bytes) -> ~88 chars base64url
        assert len(keys["public_key"]) > 80

    def test_generate_vapid_keys_are_unique(self):
        keys1 = _generate_vapid_keys()
        keys2 = _generate_vapid_keys()
        assert keys1["public_key"] != keys2["public_key"]


class TestPushServiceInitialization:
    """Tests for push service initialization."""

    def test_initialize_generates_keys_when_none_exist(self, tmp_path):
        with patch("app.services.push_service.get_app_data_dir", return_value=tmp_path):
            service = PushService()
            service.initialize()

        assert service.available
        assert service.public_key
        assert (tmp_path / "vapid_keys.json").exists()

    def test_initialize_loads_existing_keys(self, tmp_path):
        keys = _generate_vapid_keys()
        (tmp_path / "vapid_keys.json").write_text(json.dumps(keys))

        with patch("app.services.push_service.get_app_data_dir", return_value=tmp_path):
            service = PushService()
            service.initialize()

        assert service.public_key == keys["public_key"]

    def test_initialize_loads_existing_subscriptions(self, tmp_path):
        keys = _generate_vapid_keys()
        (tmp_path / "vapid_keys.json").write_text(json.dumps(keys))
        subs = {"Student1": [{"endpoint": "https://example.com/push"}]}
        (tmp_path / "push_subscriptions.json").write_text(json.dumps(subs))

        with patch("app.services.push_service.get_app_data_dir", return_value=tmp_path):
            service = PushService()
            service.initialize()

        assert service._subscriptions == subs


class TestSubscriptionManagement:
    """Tests for subscription add/remove."""

    @pytest.fixture
    def service(self, tmp_path):
        keys = _generate_vapid_keys()
        (tmp_path / "vapid_keys.json").write_text(json.dumps(keys))
        with patch("app.services.push_service.get_app_data_dir", return_value=tmp_path):
            svc = PushService()
            svc.initialize()
            yield svc

    def test_add_subscription(self, service):
        sub = {"endpoint": "https://example.com/push", "keys": {"p256dh": "a", "auth": "b"}}
        service.add_subscription("Student1", sub)
        assert len(service._subscriptions["Student1"]) == 1

    def test_add_duplicate_replaces(self, service):
        sub = {"endpoint": "https://example.com/push", "keys": {"p256dh": "a", "auth": "b"}}
        service.add_subscription("Student1", sub)
        service.add_subscription("Student1", sub)
        assert len(service._subscriptions["Student1"]) == 1

    def test_add_different_endpoints(self, service):
        sub1 = {"endpoint": "https://example.com/push/1", "keys": {}}
        sub2 = {"endpoint": "https://example.com/push/2", "keys": {}}
        service.add_subscription("Student1", sub1)
        service.add_subscription("Student1", sub2)
        assert len(service._subscriptions["Student1"]) == 2

    def test_remove_subscription(self, service):
        sub = {"endpoint": "https://example.com/push", "keys": {}}
        service.add_subscription("Student1", sub)
        service.remove_subscription("Student1", "https://example.com/push")
        assert "Student1" not in service._subscriptions

    def test_remove_nonexistent_student(self, service):
        # Should not raise
        service.remove_subscription("Nobody", "https://example.com/push")

    def test_subscriptions_persisted(self, service, tmp_path):
        sub = {"endpoint": "https://example.com/push", "keys": {}}
        service.add_subscription("Student1", sub)

        subs_path = tmp_path / "push_subscriptions.json"
        assert subs_path.exists()
        data = json.loads(subs_path.read_text())
        assert "Student1" in data


class TestSendNotification:
    """Tests for sending push notifications."""

    @pytest.fixture
    def service(self, tmp_path):
        keys = _generate_vapid_keys()
        (tmp_path / "vapid_keys.json").write_text(json.dumps(keys))
        with patch("app.services.push_service.get_app_data_dir", return_value=tmp_path):
            svc = PushService()
            svc.initialize()
            yield svc

    @pytest.mark.asyncio
    async def test_send_returns_zero_when_no_subscriptions(self, service):
        count = await service.send_notification("Nobody", "title", "body")
        assert count == 0

    @pytest.mark.asyncio
    async def test_send_returns_zero_when_not_available(self, tmp_path):
        with patch("app.services.push_service.get_app_data_dir", return_value=tmp_path):
            svc = PushService()
            # Not initialized -> not available
            count = await svc.send_notification("Student1", "title", "body")
            assert count == 0

    @pytest.mark.asyncio
    async def test_send_calls_webpush(self, service):
        sub = {"endpoint": "https://example.com/push", "keys": {"p256dh": "a", "auth": "b"}}
        service.add_subscription("Student1", sub)

        with patch("app.services.push_service.webpush") as mock_wp:
            count = await service.send_notification("Student1", "Nová známka", "Mat: 1")
            assert count == 1
            mock_wp.assert_called_once()
            call_kwargs = mock_wp.call_args
            payload = json.loads(call_kwargs.kwargs["data"] if "data" in call_kwargs.kwargs else call_kwargs[1]["data"] if len(call_kwargs) > 1 else call_kwargs[0][1])
            assert payload["title"] == "Nová známka"
            assert payload["body"] == "Mat: 1"

    @pytest.mark.asyncio
    async def test_send_removes_expired_subscriptions(self, service):
        sub = {"endpoint": "https://example.com/push", "keys": {}}
        service.add_subscription("Student1", sub)

        from pywebpush import WebPushException
        mock_response = MagicMock()
        mock_response.status_code = 410

        with patch("app.services.push_service.webpush", side_effect=WebPushException("Gone", response=mock_response)):
            count = await service.send_notification("Student1", "title", "body")
            assert count == 0

        # Subscription should be removed
        assert not service._subscriptions.get("Student1", [])

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_all_students(self, service):
        service.add_subscription("Student1", {"endpoint": "https://a.com/push", "keys": {}})
        service.add_subscription("Student2", {"endpoint": "https://b.com/push", "keys": {}})

        with patch("app.services.push_service.webpush"):
            count = await service.broadcast_notification("title", "body")
            assert count == 2
