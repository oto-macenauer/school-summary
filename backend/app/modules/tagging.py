"""AI-powered message tagging and agenda extraction using Gemini.

One Gemini call per batch returns both the semantic tags shown on the messages
page and the calendar events / checklist tasks the message implies.  Keeping it
in a single call means adding the agenda feature costs no extra quota.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from ..core.gemini import GeminiClient
from ..models.config import DEFAULT_TAGGING_PROMPT, DEFAULT_TAGGING_SYSTEM
from .agenda import AgendaEvent, AgendaTask, parse_events, parse_tasks

_LOGGER = logging.getLogger("bakalari.tagging")

BATCH_SIZE = 5

# Bumped when the extraction contract changes, so the scheduler can tell which
# stored messages were processed by an older prompt. 1 = tags only,
# 2 = tags + calendar events + checklist tasks.
TAG_SCHEMA_VERSION = 2


@dataclass
class TemporalTag:
    """A date or date range extracted from a message."""

    date_from: date
    date_to: date | None = None
    label: str = ""


@dataclass
class MessageTags:
    """Tags extracted from a message by AI."""

    temporal: list[TemporalTag] = field(default_factory=list)
    subjects: list[str] = field(default_factory=list)
    importance: list[str] = field(default_factory=list)
    tagged_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "temporal": [
                {
                    "from": t.date_from.isoformat(),
                    "to": t.date_to.isoformat() if t.date_to else None,
                    "label": t.label,
                }
                for t in self.temporal
            ],
            "subjects": self.subjects,
            "importance": self.importance,
            "tagged_at": self.tagged_at.isoformat() if self.tagged_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MessageTags:
        temporal = []
        for t in data.get("temporal", []):
            temporal.append(
                TemporalTag(
                    date_from=date.fromisoformat(t["from"]),
                    date_to=date.fromisoformat(t["to"]) if t.get("to") else None,
                    label=t.get("label", ""),
                )
            )
        tagged_at = None
        if data.get("tagged_at"):
            try:
                tagged_at = datetime.fromisoformat(data["tagged_at"])
            except (ValueError, TypeError):
                pass
        return cls(
            temporal=temporal,
            subjects=data.get("subjects", []),
            importance=data.get("importance", []),
            tagged_at=tagged_at,
        )


@dataclass
class MessageExtraction:
    """Everything one AI pass produced for a single message."""

    tags: MessageTags
    events: list[AgendaEvent] = field(default_factory=list)
    tasks: list[AgendaTask] = field(default_factory=list)


@dataclass
class TaggableMessage:
    """A message ready for AI tagging."""

    message_id: str
    title: str
    body: str
    sent_date: date | None
    source_type: str  # "komens" | "mail" | "report"

    @property
    def source_id(self) -> str:
        """Stable id shared with the resources endpoint, e.g. ``komens-1234``."""
        return f"{self.source_type}-{self.message_id}"


class TaggingModule:
    """Uses Gemini to extract tags, calendar events and tasks from messages."""

    def __init__(
        self,
        gemini_client: GeminiClient,
        prompt_template: str | None = None,
        system_instruction: str | None = None,
    ) -> None:
        self._gemini = gemini_client
        self._prompt_template = prompt_template or None
        self._system_instruction = system_instruction or None

    async def tag_messages(
        self, messages: list[TaggableMessage],
    ) -> dict[str, MessageExtraction]:
        """Tag a list of messages using Gemini AI.

        Returns a dict mapping message_id to its extraction.
        """
        if not messages:
            return {}

        result: dict[str, MessageExtraction] = {}

        # Process in batches
        for i in range(0, len(messages), BATCH_SIZE):
            batch = messages[i : i + BATCH_SIZE]
            try:
                batch_result = await self._tag_batch(batch)
                result.update(batch_result)
            except Exception as err:
                _LOGGER.error("Failed to tag batch %d: %s", i // BATCH_SIZE, err)

        return result

    async def _tag_batch(
        self, messages: list[TaggableMessage],
    ) -> dict[str, MessageExtraction]:
        prompt = self._build_tagging_prompt(messages)
        system = self._get_system_instruction()

        try:
            response = await self._gemini.generate_content(
                prompt=prompt,
                system_instruction=system,
                max_tokens=8192,
                temperature=0.1,
            )
            return self._parse_response(response, messages)
        except Exception as err:
            _LOGGER.error("Gemini tagging request failed: %s", err)
            return {}

    @staticmethod
    def _format_messages_block(messages: list[TaggableMessage]) -> str:
        blocks = []
        for idx, msg in enumerate(messages, 1):
            date_str = msg.sent_date.isoformat() if msg.sent_date else "neznámo"
            body_preview = msg.body[:1500] if msg.body else ""
            blocks.append(
                f"--- Zpráva {idx} (ID: {msg.message_id}, datum: {date_str}) ---\n"
                f"Předmět: {msg.title}\n"
                f"Obsah: {body_preview}\n"
            )
        return "\n".join(blocks)

    def _build_tagging_prompt(self, messages: list[TaggableMessage]) -> str:
        template = self._prompt_template or DEFAULT_TAGGING_PROMPT
        # Plain substitution, not str.format: the template contains a JSON
        # schema full of braces.
        return template.replace("{today}", date.today().isoformat()).replace(
            "{messages}", self._format_messages_block(messages)
        )

    def _get_system_instruction(self) -> str:
        return self._system_instruction or DEFAULT_TAGGING_SYSTEM

    def _parse_response(
        self, response: str, messages: list[TaggableMessage],
    ) -> dict[str, MessageExtraction]:
        # Strip markdown code block wrapping if present
        text = response.strip()
        if text.startswith("```"):
            # Remove ```json or ``` prefix and trailing ```
            text = re.sub(r"^```(?:json)?\s*\n?", "", text)
            text = re.sub(r"\n?```\s*$", "", text)

        try:
            data = json.loads(text)
        except json.JSONDecodeError as err:
            _LOGGER.warning("Failed to parse tagging response JSON: %s", err)
            return {}

        if not isinstance(data, dict):
            _LOGGER.warning("Tagging response is not a dict")
            return {}

        result: dict[str, MessageExtraction] = {}
        now = datetime.now()

        for idx, msg in enumerate(messages, 1):
            entry = data.get(str(idx))
            if not entry or not isinstance(entry, dict):
                continue

            temporal: list[TemporalTag] = []
            for t in entry.get("temporal", []):
                if not isinstance(t, dict) or "from" not in t:
                    continue
                try:
                    date_from = date.fromisoformat(t["from"])
                    date_to = date.fromisoformat(t["to"]) if t.get("to") else None
                    temporal.append(
                        TemporalTag(
                            date_from=date_from,
                            date_to=date_to,
                            label=t.get("label", ""),
                        )
                    )
                except (ValueError, TypeError):
                    continue

            # Fallback: if no temporal tags, use sent date
            if not temporal and msg.sent_date:
                temporal.append(
                    TemporalTag(date_from=msg.sent_date, label="datum odeslání")
                )

            subjects = [
                s for s in entry.get("subjects", []) if isinstance(s, str)
            ]
            importance = [
                i for i in entry.get("importance", []) if isinstance(i, str)
            ]

            result[msg.message_id] = MessageExtraction(
                tags=MessageTags(
                    temporal=temporal,
                    subjects=subjects,
                    importance=importance,
                    tagged_at=now,
                ),
                events=parse_events(
                    entry.get("events"), msg.source_id, msg.source_type, now,
                ),
                tasks=parse_tasks(
                    entry.get("tasks"), msg.source_id, msg.source_type, now,
                ),
            )

        return result
