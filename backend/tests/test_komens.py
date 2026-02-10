"""Tests for the komens module."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.komens import (
    Attachment,
    KomensModule,
    LifetimeType,
    Message,
    MessagesData,
    Sender,
)

from .conftest import load_fixture


@pytest.fixture
def komens_response() -> dict[str, Any]:
    """Load komens fixture."""
    return load_fixture("komens_response.json")


class TestLifetimeType:
    """Tests for LifetimeType enum."""

    def test_from_string_to_read(self) -> None:
        """Test parsing ToRead."""
        assert LifetimeType.from_string("ToRead") == LifetimeType.TO_READ

    def test_from_string_to_confirm(self) -> None:
        """Test parsing ToConfirm."""
        assert LifetimeType.from_string("ToConfirm") == LifetimeType.TO_CONFIRM

    def test_from_string_unknown(self) -> None:
        """Test parsing unknown value."""
        assert LifetimeType.from_string("Unknown") == LifetimeType.UNDEFINED


class TestSender:
    """Tests for Sender dataclass."""

    def test_from_api_response(self, komens_response: dict[str, Any]) -> None:
        """Test creating Sender from API response."""
        sender_data = komens_response["Messages"][0]["Sender"]
        sender = Sender.from_api_response(sender_data)

        assert sender.sender_id == "T1"
        assert sender.sender_type == "teacher"
        assert sender.name == "Jan Novák"


class TestAttachment:
    """Tests for Attachment dataclass."""

    def test_from_api_response(self, komens_response: dict[str, Any]) -> None:
        """Test creating Attachment from API response."""
        # Third message has attachment
        att_data = komens_response["Messages"][2]["Attachments"][0]
        att = Attachment.from_api_response(att_data)

        assert att.attachment_id == "ATT001"
        assert att.name == "diplom.pdf"
        assert att.size == 125000
        assert att.mime_type == "application/pdf"


class TestMessage:
    """Tests for Message dataclass."""

    def test_from_api_response(self, komens_response: dict[str, Any]) -> None:
        """Test creating Message from API response."""
        msg_data = komens_response["Messages"][0]
        msg = Message.from_api_response(msg_data)

        assert msg.message_id == "MSG001"
        assert msg.title == "Informace o třídní schůzce"
        assert msg.is_read is False
        assert msg.can_confirm is True
        assert msg.sender is not None
        assert msg.sender.name == "Jan Novák"

    def test_plain_text(self) -> None:
        """Test HTML to plain text conversion."""
        msg = Message(
            message_id="1",
            title="Test",
            text="<p>Hello <b>World</b></p><br/>Line 2",
            sent_date=None,
            sender=None,
            is_read=False,
            is_confirmed=False,
            lifetime=LifetimeType.TO_READ,
            message_type="OBECNA",
            can_confirm=False,
            can_answer=False,
            attachments=[],
        )
        assert "Hello World" in msg.plain_text
        assert "<p>" not in msg.plain_text
        assert "<b>" not in msg.plain_text

    def test_clean_text_preserves_newlines(self) -> None:
        """Test that clean_text preserves line breaks."""
        msg = Message(
            message_id="1",
            title="Test",
            text="Line 1<br/>Line 2<p>Paragraph</p>",
            sent_date=None,
            sender=None,
            is_read=False,
            is_confirmed=False,
            lifetime=LifetimeType.TO_READ,
            message_type="OBECNA",
            can_confirm=False,
            can_answer=False,
            attachments=[],
        )
        assert "\n" in msg.clean_text

    def test_to_markdown(self) -> None:
        """Test Markdown conversion."""
        sender = Sender("T1", "teacher", "Jan Novák")
        msg = Message(
            message_id="1",
            title="Test Message",
            text="Hello World",
            sent_date=datetime(2024, 12, 10, 9, 30),
            sender=sender,
            is_read=False,
            is_confirmed=False,
            lifetime=LifetimeType.TO_READ,
            message_type="OBECNA",
            can_confirm=False,
            can_answer=False,
            attachments=[],
        )
        md = msg.to_markdown()

        assert "# Test Message" in md
        assert "**From:** Jan Novák" in md
        assert "**Date:** 2024-12-10 09:30" in md
        assert "Hello World" in md

    def test_to_markdown_with_attachments(self) -> None:
        """Test Markdown with attachments."""
        att = Attachment("A1", "file.pdf", 1000, "application/pdf")
        msg = Message(
            message_id="1",
            title="Test",
            text="Content",
            sent_date=None,
            sender=None,
            is_read=False,
            is_confirmed=False,
            lifetime=LifetimeType.TO_READ,
            message_type="OBECNA",
            can_confirm=False,
            can_answer=False,
            attachments=[att],
        )
        md = msg.to_markdown()

        assert "**Attachments:**" in md
        assert "file.pdf" in md


class TestMessagesData:
    """Tests for MessagesData dataclass."""

    def test_unread_count(self) -> None:
        """Test unread message count."""
        received = [
            MagicMock(is_read=False),
            MagicMock(is_read=True),
        ]
        noticeboard = [
            MagicMock(is_read=False),
        ]
        data = MessagesData(received=received, noticeboard=noticeboard)
        assert data.unread_count == 2

    def test_unconfirmed_count(self) -> None:
        """Test unconfirmed message count."""
        received = [
            MagicMock(can_confirm=True, is_confirmed=False),
            MagicMock(can_confirm=True, is_confirmed=True),
            MagicMock(can_confirm=False, is_confirmed=False),
        ]
        data = MessagesData(received=received)
        assert data.unconfirmed_count == 1

    def test_get_message(self) -> None:
        """Test getting message by ID."""
        msg1 = MagicMock(message_id="MSG001")
        msg2 = MagicMock(message_id="MSG002")
        data = MessagesData(received=[msg1], noticeboard=[msg2])

        assert data.get_message("MSG001") == msg1
        assert data.get_message("MSG002") == msg2
        assert data.get_message("XXX") is None

    def test_to_summary_dict(self) -> None:
        """Test summary dictionary."""
        msg = MagicMock(
            message_id="MSG001",
            title="Test",
            sender=MagicMock(name="Sender"),
            sent_date=datetime(2024, 12, 10),
            is_read=False,
        )
        data = MessagesData(received=[msg])

        summary = data.to_summary_dict()
        assert "unread_count" in summary
        assert "recent_messages" in summary


class TestKomensModule:
    """Tests for KomensModule class."""

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        """Create mock client."""
        client = MagicMock()
        client.get = AsyncMock()
        client.post = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_get_received_messages(
        self, mock_client: MagicMock, komens_response: dict[str, Any]
    ) -> None:
        """Test fetching received messages."""
        mock_client.post.return_value = komens_response

        module = KomensModule(mock_client)
        result = await module.get_received_messages()

        assert len(result) == 3
        assert result[0].title == "Informace o třídní schůzce"

    @pytest.mark.asyncio
    async def test_get_all_messages(
        self, mock_client: MagicMock, komens_response: dict[str, Any]
    ) -> None:
        """Test fetching all messages."""
        mock_client.post.return_value = komens_response

        module = KomensModule(mock_client)
        result = await module.get_all_messages()

        assert isinstance(result, MessagesData)
        assert len(result.received) == 3
        assert len(result.noticeboard) == 3

    @pytest.mark.asyncio
    async def test_messages_sorted_by_date(
        self, mock_client: MagicMock, komens_response: dict[str, Any]
    ) -> None:
        """Test that messages are sorted by date (newest first)."""
        mock_client.post.return_value = komens_response

        module = KomensModule(mock_client)
        result = await module.get_received_messages()

        # First message should be newest
        assert result[0].message_id == "MSG001"  # Dec 10
        assert result[1].message_id == "MSG002"  # Dec 9
        assert result[2].message_id == "MSG003"  # Dec 8
