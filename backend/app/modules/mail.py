"""Mail module for Gmail messages synced via Google Drive."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

_LOGGER = logging.getLogger("bakalari.mail")


@dataclass
class MailMessage:
    """A single email message parsed from a markdown file."""

    file_id: str
    subject: str
    sender: str
    date: datetime | None
    body: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.file_id,
            "subject": self.subject,
            "sender": self.sender,
            "date": self.date.isoformat() if self.date else None,
            "body": self.body,
        }

    @classmethod
    def from_markdown(cls, file_id: str, content: str) -> MailMessage:
        """Parse a mail message from markdown with YAML frontmatter.

        Expected format::

            ---
            subject: Email Subject
            from: sender@example.com
            date: 2025-01-15T10:30:00
            ---

            Email body text here...
        """
        subject = ""
        sender = ""
        date = None
        body = content

        parts = content.split("---", 2)
        if len(parts) >= 3:
            frontmatter = parts[1].strip()
            body = parts[2].strip()

            for line in frontmatter.splitlines():
                if ":" in line:
                    key, _, value = line.partition(":")
                    key = key.strip().lower()
                    value = value.strip().strip('"').strip("'")

                    if key == "subject":
                        subject = value
                    elif key == "from":
                        sender = value
                    elif key == "date":
                        try:
                            date = datetime.fromisoformat(value)
                        except ValueError:
                            _LOGGER.warning("Invalid date in mail: %s", value)

        return cls(
            file_id=file_id,
            subject=subject or "(No subject)",
            sender=sender or "(Unknown sender)",
            date=date,
            body=body,
        )


@dataclass
class MailData:
    """Container for all mail messages for a student."""

    messages: list[MailMessage] = field(default_factory=list)

    @property
    def total_count(self) -> int:
        return len(self.messages)

    def to_summary_dict(self) -> dict[str, Any]:
        sorted_messages = sorted(
            self.messages,
            key=lambda m: m.date or datetime.min,
            reverse=True,
        )
        return {
            "total_count": self.total_count,
            "messages": [m.to_dict() for m in sorted_messages],
        }
