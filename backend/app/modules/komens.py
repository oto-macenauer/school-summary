"""Komens (messages) module for Bakalari API."""

from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from ..core.client import BakalariClient
from ..const import (
    API_KOMENS_NOTICEBOARD,
    API_KOMENS_RECEIVED,
    API_KOMENS_SENT,
    API_KOMENS_UNREAD,
)

_LOGGER = logging.getLogger("bakalari.komens")


class MessageType(Enum):
    """Types of Komens messages."""

    RECEIVED = "received"
    SENT = "sent"
    NOTICEBOARD = "noticeboard"


class LifetimeType(Enum):
    """Message lifetime types."""

    TO_READ = "ToRead"
    TO_CONFIRM = "ToConfirm"
    UNLIMITED = "Unlimited"
    UNDEFINED = "Undefined"

    @classmethod
    def from_string(cls, value: str) -> LifetimeType:
        """Create LifetimeType from string."""
        for member in cls:
            if member.value == value:
                return member
        return cls.UNDEFINED


@dataclass
class Attachment:
    """Represents a message attachment."""

    attachment_id: str
    name: str
    size: int
    mime_type: str

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> Attachment:
        """Create Attachment from API response."""
        return cls(
            attachment_id=data.get("Id", ""),
            name=data.get("Name", ""),
            size=data.get("Size", 0),
            mime_type=data.get("Type", ""),
        )


@dataclass
class Sender:
    """Represents the sender of a message."""

    sender_id: str
    sender_type: str
    name: str

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> Sender:
        """Create Sender from API response."""
        return cls(
            sender_id=data.get("Id", ""),
            sender_type=data.get("Type", ""),
            name=data.get("Name", ""),
        )


@dataclass
class Message:
    """Represents a Komens message."""

    message_id: str
    title: str
    text: str
    sent_date: datetime | None
    sender: Sender | None
    is_read: bool
    is_confirmed: bool
    lifetime: LifetimeType
    message_type: str
    can_confirm: bool
    can_answer: bool
    attachments: list[Attachment] = field(default_factory=list)

    @property
    def plain_text(self) -> str:
        """Get plain text version of the message (HTML decoded)."""
        # Decode HTML entities
        text = html.unescape(self.text)
        # Remove HTML tags
        text = re.sub(r"<[^>]+>", "", text)
        # Clean up whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @property
    def clean_text(self) -> str:
        """Get text with basic formatting preserved."""
        text = html.unescape(self.text)
        # Convert <br> to newlines
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
        # Convert <p> to double newlines
        text = re.sub(r"<p[^>]*>", "\n\n", text, flags=re.IGNORECASE)
        text = re.sub(r"</p>", "", text, flags=re.IGNORECASE)
        # Remove remaining HTML tags
        text = re.sub(r"<[^>]+>", "", text)
        # Clean up excessive newlines
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def to_markdown(self) -> str:
        """Convert message to Markdown format."""
        lines = [
            f"# {self.title}",
            "",
            f"**From:** {self.sender.name if self.sender else 'Unknown'}",
            f"**Date:** {self.sent_date.strftime('%Y-%m-%d %H:%M') if self.sent_date else 'Unknown'}",
            f"**Type:** {self.message_type}",
            f"**Read:** {'Yes' if self.is_read else 'No'}",
        ]

        if self.is_confirmed:
            lines.append("**Confirmed:** Yes")

        if self.attachments:
            lines.append("")
            lines.append("**Attachments:**")
            for att in self.attachments:
                lines.append(f"- {att.name} ({att.size} bytes)")

        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append(self.clean_text)

        return "\n".join(lines)

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> Message:
        """Create Message from API response."""
        sent_date = None
        if data.get("SentDate"):
            try:
                sent_date = datetime.fromisoformat(
                    data["SentDate"].replace("Z", "+00:00")
                )
            except ValueError:
                pass

        sender_data = data.get("Sender")
        sender = Sender.from_api_response(sender_data) if sender_data else None

        attachments = [
            Attachment.from_api_response(a) for a in data.get("Attachments", [])
        ]

        return cls(
            message_id=data.get("Id", ""),
            title=data.get("Title", ""),
            text=data.get("Text", ""),
            sent_date=sent_date,
            sender=sender,
            is_read=data.get("Read", False),
            is_confirmed=data.get("Confirmed", False),
            lifetime=LifetimeType.from_string(data.get("LifeTime", "")),
            message_type=data.get("Type", ""),
            can_confirm=data.get("CanConfirm", False),
            can_answer=data.get("CanAnswer", False),
            attachments=attachments,
        )


@dataclass
class MessagesData:
    """Contains all messages data."""

    received: list[Message] = field(default_factory=list)
    noticeboard: list[Message] = field(default_factory=list)
    sent: list[Message] = field(default_factory=list)

    @property
    def all_messages(self) -> list[Message]:
        """Get all messages combined."""
        return self.received + self.noticeboard + self.sent

    @property
    def unread_count(self) -> int:
        """Get count of unread messages."""
        return sum(1 for m in self.received + self.noticeboard if not m.is_read)

    @property
    def unconfirmed_count(self) -> int:
        """Get count of messages requiring confirmation."""
        return sum(
            1
            for m in self.received + self.noticeboard
            if m.can_confirm and not m.is_confirmed
        )

    def get_message(self, message_id: str) -> Message | None:
        """Get message by ID."""
        for msg in self.all_messages:
            if msg.message_id == message_id:
                return msg
        return None

    def to_summary_dict(self) -> dict[str, Any]:
        """Convert to a summary dictionary for sensor state."""
        sorted_messages = sorted(
            self.received + self.noticeboard,
            key=lambda x: x.sent_date or datetime.min,
            reverse=True,
        )

        return {
            "unread_count": self.unread_count,
            "unconfirmed_count": self.unconfirmed_count,
            "received_count": len(self.received),
            "noticeboard_count": len(self.noticeboard),
            "recent_messages": [
                {
                    "id": m.message_id,
                    "title": m.title,
                    "sender": m.sender.name if m.sender else None,
                    "date": m.sent_date.isoformat() if m.sent_date else None,
                    "is_read": m.is_read,
                    "text": m.clean_text or "",
                    "has_attachments": len(m.attachments) > 0,
                }
                for m in sorted_messages
            ],
        }


class KomensModule:
    """Module for fetching and managing Komens messages."""

    def __init__(self, client: BakalariClient) -> None:
        """Initialize the Komens module.

        Args:
            client: Authenticated Bakalari API client
        """
        self._client = client

    async def get_received_messages(self) -> list[Message]:
        """Get received messages.

        Returns:
            List of received messages
        """
        # Note: Komens API requires POST with NO body (not even empty JSON)
        response = await self._client.post(API_KOMENS_RECEIVED)
        messages = self._parse_messages_response(response)
        _LOGGER.debug("Fetched %d received messages", len(messages))
        return messages

    async def get_noticeboard_messages(self) -> list[Message]:
        """Get noticeboard messages.

        Returns:
            List of noticeboard messages
        """
        # Note: Komens API requires POST with NO body (not even empty JSON)
        response = await self._client.post(API_KOMENS_NOTICEBOARD)
        return self._parse_messages_response(response)

    async def get_sent_messages(self) -> list[Message]:
        """Get sent messages.

        Returns:
            List of sent messages
        """
        # Note: Komens API requires POST with NO body (not even empty JSON)
        response = await self._client.post(API_KOMENS_SENT)
        return self._parse_messages_response(response)

    async def get_unread_count(self) -> int:
        """Get count of unread messages.

        Returns:
            Number of unread messages
        """
        response = await self._client.get(API_KOMENS_UNREAD)
        # Response is just an integer
        if isinstance(response, int):
            return response
        return response.get("Count", 0)

    async def get_all_messages(self) -> MessagesData:
        """Get all messages (received, noticeboard, sent).

        Returns:
            MessagesData containing all message types
        """
        received = await self.get_received_messages()

        # Noticeboard is optional - not all schools have it enabled
        noticeboard = []
        try:
            noticeboard = await self.get_noticeboard_messages()
        except Exception as err:
            _LOGGER.debug("Noticeboard not available: %s", err)

        # Sent messages are optional
        sent = []
        try:
            sent = await self.get_sent_messages()
        except Exception as err:
            _LOGGER.debug("Sent messages not available: %s", err)

        return MessagesData(
            received=received,
            noticeboard=noticeboard,
            sent=sent,
        )

    def _parse_messages_response(self, response: dict[str, Any]) -> list[Message]:
        """Parse messages from API response.

        Args:
            response: Raw API response

        Returns:
            List of Message objects
        """
        _LOGGER.debug(
            "Parsing messages response, keys: %s, Messages count: %d",
            list(response.keys()) if response else [],
            len(response.get("Messages", [])) if response else 0,
        )
        messages = []
        for msg_data in response.get("Messages", []):
            message = Message.from_api_response(msg_data)
            messages.append(message)

        # Sort by date, newest first
        messages.sort(
            key=lambda m: m.sent_date or datetime.min,
            reverse=True,
        )

        return messages
