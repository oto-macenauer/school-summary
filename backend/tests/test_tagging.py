"""Tests for the tagging module."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.tagging import (
    BATCH_SIZE,
    MessageTags,
    TaggableMessage,
    TaggingModule,
    TemporalTag,
)


FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestTemporalTag:
    """Tests for TemporalTag dataclass."""

    def test_creation_single_day(self) -> None:
        tag = TemporalTag(date_from=date(2026, 3, 10))
        assert tag.date_from == date(2026, 3, 10)
        assert tag.date_to is None
        assert tag.label == ""

    def test_creation_range(self) -> None:
        tag = TemporalTag(
            date_from=date(2026, 3, 10),
            date_to=date(2026, 3, 14),
            label="příští týden",
        )
        assert tag.date_from == date(2026, 3, 10)
        assert tag.date_to == date(2026, 3, 14)
        assert tag.label == "příští týden"


class TestMessageTags:
    """Tests for MessageTags dataclass."""

    def test_to_dict(self) -> None:
        tags = MessageTags(
            temporal=[
                TemporalTag(date_from=date(2026, 3, 10), label="test"),
                TemporalTag(date_from=date(2026, 3, 12), date_to=date(2026, 3, 14)),
            ],
            subjects=["Matematika", "Fyzika"],
            importance=["test", "homework"],
            tagged_at=datetime(2026, 3, 8, 12, 0, 0),
        )
        d = tags.to_dict()
        assert len(d["temporal"]) == 2
        assert d["temporal"][0]["from"] == "2026-03-10"
        assert d["temporal"][0]["to"] is None
        assert d["temporal"][1]["to"] == "2026-03-14"
        assert d["subjects"] == ["Matematika", "Fyzika"]
        assert d["importance"] == ["test", "homework"]
        assert "2026-03-08" in d["tagged_at"]

    def test_from_dict(self) -> None:
        data = {
            "temporal": [
                {"from": "2026-03-10", "to": None, "label": "test"},
            ],
            "subjects": ["Český jazyk"],
            "importance": ["info"],
            "tagged_at": "2026-03-08T12:00:00",
        }
        tags = MessageTags.from_dict(data)
        assert len(tags.temporal) == 1
        assert tags.temporal[0].date_from == date(2026, 3, 10)
        assert tags.temporal[0].date_to is None
        assert tags.subjects == ["Český jazyk"]
        assert tags.importance == ["info"]
        assert tags.tagged_at == datetime(2026, 3, 8, 12, 0, 0)

    def test_round_trip(self) -> None:
        original = MessageTags(
            temporal=[
                TemporalTag(date_from=date(2026, 3, 10), date_to=date(2026, 3, 12), label="akce"),
            ],
            subjects=["Matematika"],
            importance=["event"],
            tagged_at=datetime(2026, 3, 8, 15, 30, 0),
        )
        d = original.to_dict()
        restored = MessageTags.from_dict(d)
        assert len(restored.temporal) == 1
        assert restored.temporal[0].date_from == original.temporal[0].date_from
        assert restored.temporal[0].date_to == original.temporal[0].date_to
        assert restored.temporal[0].label == original.temporal[0].label
        assert restored.subjects == original.subjects
        assert restored.importance == original.importance
        assert restored.tagged_at == original.tagged_at

    def test_from_dict_empty(self) -> None:
        tags = MessageTags.from_dict({})
        assert tags.temporal == []
        assert tags.subjects == []
        assert tags.importance == []
        assert tags.tagged_at is None

    def test_to_dict_no_tagged_at(self) -> None:
        tags = MessageTags()
        d = tags.to_dict()
        assert d["tagged_at"] is None


class TestTaggingModule:
    """Tests for TaggingModule class."""

    @pytest.fixture
    def mock_gemini(self) -> MagicMock:
        client = MagicMock()
        client.generate_content = AsyncMock()
        return client

    @pytest.fixture
    def tagger(self, mock_gemini: MagicMock) -> TaggingModule:
        return TaggingModule(mock_gemini)

    @pytest.fixture
    def sample_messages(self) -> list[TaggableMessage]:
        return [
            TaggableMessage(
                message_id="MSG001",
                title="Test z matematiky",
                body="Příští pondělí bude test z rovnic.",
                sent_date=date(2026, 3, 5),
                source_type="komens",
            ),
            TaggableMessage(
                message_id="MSG002",
                title="Domácí úkol",
                body="Vypracujte cvičení 5-10 ze strany 42.",
                sent_date=date(2026, 3, 6),
                source_type="komens",
            ),
        ]

    def test_build_tagging_prompt(
        self, tagger: TaggingModule, sample_messages: list[TaggableMessage],
    ) -> None:
        prompt = tagger._build_tagging_prompt(sample_messages)
        assert "MSG001" in prompt
        assert "MSG002" in prompt
        assert "Test z matematiky" in prompt
        assert "Domácí úkol" in prompt
        assert "2026-03-05" in prompt
        assert "JSON" in prompt

    def test_parse_response_valid(
        self, tagger: TaggingModule, sample_messages: list[TaggableMessage],
    ) -> None:
        fixture = (FIXTURES_DIR / "tagging_response.json").read_text()
        # Use only first 2 messages from fixture
        response_data = json.loads(fixture)
        trimmed = {"1": response_data["1"], "2": response_data["2"]}
        response = json.dumps(trimmed)

        result = tagger._parse_response(response, sample_messages)
        assert "MSG001" in result
        assert "MSG002" in result
        assert result["MSG001"].subjects == ["Matematika"]
        assert "test" in result["MSG001"].importance
        assert result["MSG001"].temporal[0].date_from == date(2026, 3, 10)

    def test_parse_response_malformed_json(
        self, tagger: TaggingModule, sample_messages: list[TaggableMessage],
    ) -> None:
        result = tagger._parse_response("not valid json {{{", sample_messages)
        assert result == {}

    def test_parse_response_markdown_wrapped(
        self, tagger: TaggingModule, sample_messages: list[TaggableMessage],
    ) -> None:
        fixture = (FIXTURES_DIR / "tagging_response.json").read_text()
        data = json.loads(fixture)
        trimmed = json.dumps({"1": data["1"], "2": data["2"]})
        wrapped = f"```json\n{trimmed}\n```"

        result = tagger._parse_response(wrapped, sample_messages)
        assert "MSG001" in result
        assert "MSG002" in result

    def test_parse_response_fallback_sent_date(
        self, tagger: TaggingModule,
    ) -> None:
        """Messages without temporal tags should fallback to sent_date."""
        messages = [
            TaggableMessage(
                message_id="MSG_NODATE",
                title="Info",
                body="Just info",
                sent_date=date(2026, 3, 1),
                source_type="komens",
            ),
        ]
        response = json.dumps({
            "1": {"temporal": [], "subjects": [], "importance": ["info"]},
        })
        result = tagger._parse_response(response, messages)
        assert "MSG_NODATE" in result
        assert result["MSG_NODATE"].temporal[0].date_from == date(2026, 3, 1)
        assert result["MSG_NODATE"].temporal[0].label == "datum odeslání"

    @pytest.mark.asyncio
    async def test_tag_messages_success(
        self,
        tagger: TaggingModule,
        mock_gemini: MagicMock,
        sample_messages: list[TaggableMessage],
    ) -> None:
        fixture = (FIXTURES_DIR / "tagging_response.json").read_text()
        data = json.loads(fixture)
        trimmed = json.dumps({"1": data["1"], "2": data["2"]})
        mock_gemini.generate_content.return_value = trimmed

        result = await tagger.tag_messages(sample_messages)
        assert "MSG001" in result
        assert "MSG002" in result
        mock_gemini.generate_content.assert_called_once()

    @pytest.mark.asyncio
    async def test_tag_messages_batch_splitting(
        self, tagger: TaggingModule, mock_gemini: MagicMock,
    ) -> None:
        """12 messages should result in 2 Gemini calls (10+2)."""
        messages = [
            TaggableMessage(
                message_id=f"MSG{i:03d}",
                title=f"Message {i}",
                body=f"Body {i}",
                sent_date=date(2026, 3, 1),
                source_type="komens",
            )
            for i in range(12)
        ]
        mock_gemini.generate_content.return_value = json.dumps({})

        await tagger.tag_messages(messages)
        assert mock_gemini.generate_content.call_count == 2

    @pytest.mark.asyncio
    async def test_tag_messages_gemini_error(
        self, tagger: TaggingModule, mock_gemini: MagicMock,
        sample_messages: list[TaggableMessage],
    ) -> None:
        """Gemini error should return empty dict gracefully."""
        mock_gemini.generate_content.side_effect = Exception("API error")

        result = await tagger.tag_messages(sample_messages)
        assert result == {}

    @pytest.mark.asyncio
    async def test_tag_messages_empty(
        self, tagger: TaggingModule,
    ) -> None:
        result = await tagger.tag_messages([])
        assert result == {}

    def test_get_system_instruction(self, tagger: TaggingModule) -> None:
        instruction = tagger._get_system_instruction()
        assert "JSON" in instruction
