"""AI-powered message tagging module using Gemini."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from ..core.gemini import GeminiClient

_LOGGER = logging.getLogger("bakalari.tagging")

BATCH_SIZE = 10


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
class TaggableMessage:
    """A message ready for AI tagging."""

    message_id: str
    title: str
    body: str
    sent_date: date | None
    source_type: str  # "komens" | "mail" | "report"


class TaggingModule:
    """Uses Gemini to extract semantic tags from messages."""

    def __init__(self, gemini_client: GeminiClient) -> None:
        self._gemini = gemini_client

    async def tag_messages(
        self, messages: list[TaggableMessage],
    ) -> dict[str, MessageTags]:
        """Tag a list of messages using Gemini AI.

        Returns a dict mapping message_id to extracted tags.
        """
        if not messages:
            return {}

        result: dict[str, MessageTags] = {}

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
    ) -> dict[str, MessageTags]:
        prompt = self._build_tagging_prompt(messages)
        system = self._get_system_instruction()

        try:
            response = await self._gemini.generate_content(
                prompt=prompt,
                system_instruction=system,
                max_tokens=2048,
                temperature=0.1,
            )
            return self._parse_response(response, messages)
        except Exception as err:
            _LOGGER.error("Gemini tagging request failed: %s", err)
            return {}

    def _build_tagging_prompt(self, messages: list[TaggableMessage]) -> str:
        lines = [
            "Analyzuj následující zprávy a extrahuj z nich tagy.\n",
            "Pro každou zprávu urči:",
            "1. temporal - seznam dat nebo rozsahů dat, ke kterým se zpráva vztahuje",
            "   (format: {\"from\": \"YYYY-MM-DD\", \"to\": \"YYYY-MM-DD\" nebo null, \"label\": \"popis\"})",
            "   Pokud zpráva zmiňuje relativní datum (příští pondělí, za týden), "
            "vyřeš ho vzhledem k datu odeslání.",
            "   Každá zpráva musí mít alespoň 1 temporal tag (fallback: datum odeslání).",
            "2. subjects - seznam školních předmětů zmíněných ve zprávě",
            "3. importance - seznam kategorií: test, homework, trip, event, absence, "
            "schedule_change, important, info\n",
            "Zprávy:\n",
        ]
        for idx, msg in enumerate(messages, 1):
            date_str = msg.sent_date.isoformat() if msg.sent_date else "neznámo"
            body_preview = msg.body[:800] if msg.body else ""
            lines.append(
                f"--- Zpráva {idx} (ID: {msg.message_id}, datum: {date_str}) ---\n"
                f"Předmět: {msg.title}\n"
                f"Obsah: {body_preview}\n"
            )

        lines.append(
            '\nOdpověz POUZE validním JSON objektem ve formátu:\n'
            '{"1": {"temporal": [...], "subjects": [...], "importance": [...]}, '
            '"2": {...}, ...}\n'
            "Bez dalšího textu."
        )
        return "\n".join(lines)

    def _get_system_instruction(self) -> str:
        return (
            "Jsi školní asistent, který analyzuje zprávy a extrahuje z nich strukturované tagy. "
            "Odpovídej POUZE validním JSON. Žádný další text. "
            "Předměty piš v češtině (Matematika, Fyzika, Český jazyk, atd.). "
            "Kategorie importance používej z daného seznamu."
        )

    def _parse_response(
        self, response: str, messages: list[TaggableMessage],
    ) -> dict[str, MessageTags]:
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

        result: dict[str, MessageTags] = {}
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

            result[msg.message_id] = MessageTags(
                temporal=temporal,
                subjects=subjects,
                importance=importance,
                tagged_at=now,
            )

        return result
