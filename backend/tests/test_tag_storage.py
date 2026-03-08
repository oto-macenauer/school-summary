"""Tests for the tag storage module."""

from __future__ import annotations

import tempfile
from datetime import date, datetime
from pathlib import Path

import pytest

from app.modules.tagging import MessageTags, TemporalTag
from app.storage.tag_storage import TagStorage


class TestTagStorage:
    """Tests for TagStorage static methods."""

    @pytest.fixture
    def temp_dir(self) -> Path:
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def sample_md(self, temp_dir: Path) -> Path:
        """Create a sample markdown file with frontmatter."""
        path = temp_dir / "test_message.md"
        content = (
            "---\n"
            "message_id: MSG001\n"
            "title: Test zpráva\n"
            "sender: Jan Novák\n"
            "date: 2026-03-05T10:00:00\n"
            "type: OBECNA\n"
            "read: False\n"
            "---\n"
            "\n"
            "# Test zpráva\n"
            "\n"
            "Obsah zprávy zde.\n"
        )
        path.write_text(content, encoding="utf-8")
        return path

    @pytest.fixture
    def sample_tags(self) -> MessageTags:
        return MessageTags(
            temporal=[
                TemporalTag(date_from=date(2026, 3, 10), label="příští pondělí"),
                TemporalTag(date_from=date(2026, 3, 12), date_to=date(2026, 3, 14)),
            ],
            subjects=["Matematika"],
            importance=["test"],
            tagged_at=datetime(2026, 3, 8, 12, 0, 0),
        )

    def test_read_tags_untagged_returns_none(self, sample_md: Path) -> None:
        result = TagStorage.read_tags(sample_md)
        assert result is None

    def test_is_tagged_untagged(self, sample_md: Path) -> None:
        assert TagStorage.is_tagged(sample_md) is False

    def test_write_tags(self, sample_md: Path, sample_tags: MessageTags) -> None:
        TagStorage.write_tags(sample_md, sample_tags)
        content = sample_md.read_text(encoding="utf-8")
        assert "tags_temporal:" in content
        assert "tags_subjects:" in content
        assert "tags_importance:" in content
        assert "tagged_at:" in content

    def test_write_tags_preserves_body(self, sample_md: Path, sample_tags: MessageTags) -> None:
        TagStorage.write_tags(sample_md, sample_tags)
        content = sample_md.read_text(encoding="utf-8")
        assert "Obsah zprávy zde." in content
        assert "# Test zpráva" in content

    def test_write_tags_preserves_frontmatter(self, sample_md: Path, sample_tags: MessageTags) -> None:
        TagStorage.write_tags(sample_md, sample_tags)
        content = sample_md.read_text(encoding="utf-8")
        assert "message_id: MSG001" in content
        assert "sender: Jan Novák" in content

    def test_is_tagged_after_write(self, sample_md: Path, sample_tags: MessageTags) -> None:
        TagStorage.write_tags(sample_md, sample_tags)
        assert TagStorage.is_tagged(sample_md) is True

    def test_read_tags_round_trip(self, sample_md: Path, sample_tags: MessageTags) -> None:
        TagStorage.write_tags(sample_md, sample_tags)
        result = TagStorage.read_tags(sample_md)

        assert result is not None
        assert len(result.temporal) == 2
        assert result.temporal[0].date_from == date(2026, 3, 10)
        assert result.temporal[0].label == "příští pondělí"
        assert result.temporal[1].date_to == date(2026, 3, 14)
        assert result.subjects == ["Matematika"]
        assert result.importance == ["test"]
        assert result.tagged_at == datetime(2026, 3, 8, 12, 0, 0)

    def test_write_tags_overwrites_existing(self, sample_md: Path) -> None:
        """Writing tags twice should overwrite, not duplicate."""
        tags1 = MessageTags(
            temporal=[TemporalTag(date_from=date(2026, 3, 10))],
            subjects=["Matematika"],
            importance=["test"],
            tagged_at=datetime(2026, 3, 8, 12, 0, 0),
        )
        tags2 = MessageTags(
            temporal=[TemporalTag(date_from=date(2026, 3, 15))],
            subjects=["Fyzika"],
            importance=["homework"],
            tagged_at=datetime(2026, 3, 9, 12, 0, 0),
        )

        TagStorage.write_tags(sample_md, tags1)
        TagStorage.write_tags(sample_md, tags2)

        result = TagStorage.read_tags(sample_md)
        assert result is not None
        assert result.subjects == ["Fyzika"]
        assert result.importance == ["homework"]
        assert result.temporal[0].date_from == date(2026, 3, 15)

        # Ensure no duplicate lines
        content = sample_md.read_text(encoding="utf-8")
        assert content.count("tags_temporal:") == 1
        assert content.count("tags_subjects:") == 1

    def test_read_tags_nonexistent_file(self, temp_dir: Path) -> None:
        result = TagStorage.read_tags(temp_dir / "nonexistent.md")
        assert result is None

    def test_is_tagged_nonexistent_file(self, temp_dir: Path) -> None:
        assert TagStorage.is_tagged(temp_dir / "nonexistent.md") is False

    def test_parse_frontmatter(self) -> None:
        content = (
            "---\n"
            "message_id: MSG001\n"
            "title: Test\n"
            'date: "2026-03-05T10:00:00"\n'
            "---\n"
            "\nBody text\n"
        )
        fm = TagStorage.parse_frontmatter(content)
        assert fm["message_id"] == "MSG001"
        assert fm["title"] == "Test"
        assert fm["date"] == "2026-03-05T10:00:00"

    def test_parse_frontmatter_no_frontmatter(self) -> None:
        result = TagStorage.parse_frontmatter("Just plain text")
        assert result == {}

    def test_write_tags_mail_format(self, temp_dir: Path) -> None:
        """Test tags on mail-style frontmatter (with quoted values)."""
        path = temp_dir / "mail_msg.md"
        content = (
            "---\n"
            "file_id: abc123\n"
            'subject: "Domácí úkol"\n'
            'from: "teacher@school.cz"\n'
            'date: "2026-03-06T14:00:00"\n'
            "---\n"
            "\nÚkol text here.\n"
        )
        path.write_text(content, encoding="utf-8")

        tags = MessageTags(
            temporal=[TemporalTag(date_from=date(2026, 3, 8))],
            subjects=["Český jazyk"],
            importance=["homework"],
            tagged_at=datetime(2026, 3, 8, 15, 0, 0),
        )
        TagStorage.write_tags(path, tags)

        result = TagStorage.read_tags(path)
        assert result is not None
        assert result.subjects == ["Český jazyk"]

        content = path.read_text(encoding="utf-8")
        assert "Úkol text here." in content
        assert "file_id: abc123" in content
