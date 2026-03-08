"""Storage utilities for reading/writing message tags in markdown frontmatter."""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime
from pathlib import Path

from ..modules.tagging import MessageTags, TemporalTag

_LOGGER = logging.getLogger("bakalari.tag_storage")


class TagStorage:
    """Static methods for reading/writing tags in existing markdown files."""

    @staticmethod
    def read_tags(file_path: Path) -> MessageTags | None:
        """Read tags from a markdown file's frontmatter. Returns None if not tagged."""
        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError:
            return None

        if "tagged_at:" not in content:
            return None

        fm = TagStorage.parse_frontmatter(content)

        temporal: list[TemporalTag] = []
        raw_temporal = fm.get("tags_temporal")
        if raw_temporal:
            try:
                items = json.loads(raw_temporal)
                for t in items:
                    temporal.append(
                        TemporalTag(
                            date_from=date.fromisoformat(t["from"]),
                            date_to=date.fromisoformat(t["to"]) if t.get("to") else None,
                            label=t.get("label", ""),
                        )
                    )
            except (json.JSONDecodeError, KeyError, ValueError) as err:
                _LOGGER.warning("Failed to parse tags_temporal in %s: %s", file_path, err)

        subjects: list[str] = []
        raw_subjects = fm.get("tags_subjects")
        if raw_subjects:
            try:
                subjects = json.loads(raw_subjects)
            except json.JSONDecodeError:
                pass

        importance: list[str] = []
        raw_importance = fm.get("tags_importance")
        if raw_importance:
            try:
                importance = json.loads(raw_importance)
            except json.JSONDecodeError:
                pass

        tagged_at = None
        raw_tagged = fm.get("tagged_at")
        if raw_tagged:
            try:
                tagged_at = datetime.fromisoformat(raw_tagged)
            except ValueError:
                pass

        return MessageTags(
            temporal=temporal,
            subjects=subjects,
            importance=importance,
            tagged_at=tagged_at,
        )

    @staticmethod
    def write_tags(file_path: Path, tags: MessageTags) -> None:
        """Write tags into the frontmatter of an existing markdown file."""
        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError as err:
            _LOGGER.error("Failed to read file for tagging: %s", err)
            return

        temporal_json = json.dumps(
            [
                {
                    "from": t.date_from.isoformat(),
                    "to": t.date_to.isoformat() if t.date_to else None,
                    "label": t.label,
                }
                for t in tags.temporal
            ],
            ensure_ascii=False,
        )
        subjects_json = json.dumps(tags.subjects, ensure_ascii=False)
        importance_json = json.dumps(tags.importance, ensure_ascii=False)
        tagged_at_str = tags.tagged_at.isoformat() if tags.tagged_at else datetime.now().isoformat()

        tag_lines = [
            f"tags_temporal: {temporal_json}",
            f"tags_subjects: {subjects_json}",
            f"tags_importance: {importance_json}",
            f"tagged_at: {tagged_at_str}",
        ]

        # Remove any existing tag lines first
        lines = content.split("\n")
        cleaned: list[str] = []
        for line in lines:
            if line.startswith(("tags_temporal:", "tags_subjects:", "tags_importance:", "tagged_at:")):
                continue
            cleaned.append(line)
        content = "\n".join(cleaned)

        # Insert tag lines before the closing ---
        # Find the second --- (closing frontmatter)
        parts = content.split("---", 2)
        if len(parts) >= 3:
            # parts[0] is before first ---, parts[1] is frontmatter, parts[2] is body
            fm_content = parts[1].rstrip("\n")
            new_content = (
                parts[0]
                + "---"
                + fm_content
                + "\n"
                + "\n".join(tag_lines)
                + "\n---"
                + parts[2]
            )
        else:
            # No frontmatter found, prepend one
            new_content = (
                "---\n"
                + "\n".join(tag_lines)
                + "\n---\n"
                + content
            )

        try:
            file_path.write_text(new_content, encoding="utf-8")
        except OSError as err:
            _LOGGER.error("Failed to write tags to %s: %s", file_path, err)

    @staticmethod
    def is_tagged(file_path: Path) -> bool:
        """Quick check if a file has been tagged."""
        try:
            content = file_path.read_text(encoding="utf-8")
            return "tagged_at:" in content
        except OSError:
            return False

    @staticmethod
    def parse_frontmatter(content: str) -> dict[str, str]:
        """Extract key-value pairs from YAML frontmatter."""
        result: dict[str, str] = {}
        parts = content.split("---", 2)
        if len(parts) < 3:
            return result
        for line in parts[1].strip().splitlines():
            # Match key: value, where value may contain colons
            match = re.match(r"^(\w+):\s*(.*)$", line)
            if match:
                key = match.group(1)
                val = match.group(2).strip().strip('"')
                result[key] = val
        return result
