"""Storage module for persisting AI-generated summaries and preparations."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from ..config import get_app_data_dir
from ..modules.prepare import PrepareData
from ..modules.summary import SummaryData

_LOGGER = logging.getLogger("bakalari.ai_storage")


class AIStorage:
    """Manages persistent storage of AI-generated content as Markdown files.

    Files are stored under ``app_data/ai/{student_name}/`` with YAML-style
    frontmatter containing metadata and a prompt hash for deduplication.
    """

    def __init__(self, student_name: str) -> None:
        safe_name = re.sub(r'[<>:"/\\|?*]', "_", student_name).strip(". ") or "default"
        self._dir = get_app_data_dir() / "ai" / safe_name
        self._student_name = student_name

    @property
    def storage_path(self) -> Path:
        return self._dir

    def ensure_directory(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save_summary(self, data: SummaryData, prompt_hash: str) -> Path:
        """Save summary as ``app_data/ai/{student}/summary_{week_type}.md``."""
        self.ensure_directory()
        path = self._dir / f"summary_{data.week_type}.md"

        lines = [
            "---",
            "type: summary",
            f"student_name: {data.student_name}",
            f"week_type: {data.week_type}",
            f"week_start: {data.week_start.isoformat()}",
            f"week_end: {data.week_end.isoformat()}",
            f"messages_count: {data.messages_count}",
            f"marks_count: {data.marks_count}",
            f"generated_at: {data.generated_at.isoformat()}",
            f"prompt_hash: {prompt_hash}",
            "---",
            "",
            data.summary_text,
        ]

        content = "\n".join(lines)
        try:
            path.write_text(content, encoding="utf-8")
            _LOGGER.debug("Saved summary %s for %s", data.week_type, self._student_name)
            return path
        except OSError as err:
            _LOGGER.error("Failed to save summary: %s", err)
            raise

    def save_prepare(self, data: PrepareData, prompt_hash: str) -> Path:
        """Save preparation as ``app_data/ai/{student}/prepare_{period}.md``."""
        self.ensure_directory()
        path = self._dir / f"prepare_{data.period}.md"

        lines = [
            "---",
            "type: prepare",
            f"student_name: {data.student_name}",
            f"period: {data.period}",
            f"target_date: {data.target_date.isoformat()}",
            f"lessons_count: {data.lessons_count}",
            f"messages_count: {data.messages_count}",
            f"generated_at: {data.generated_at.isoformat()}",
            f"prompt_hash: {prompt_hash}",
            "---",
            "",
            data.preparation_text,
        ]

        content = "\n".join(lines)
        try:
            path.write_text(content, encoding="utf-8")
            _LOGGER.debug("Saved prepare %s for %s", data.period, self._student_name)
            return path
        except OSError as err:
            _LOGGER.error("Failed to save preparation: %s", err)
            raise

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def load_summary(self, week_type: str) -> tuple[SummaryData | None, str | None]:
        """Load a cached summary. Returns ``(data, prompt_hash)`` or ``(None, None)``."""
        path = self._dir / f"summary_{week_type}.md"
        if not path.exists():
            return None, None

        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            return None, None

        meta, body = self._parse_frontmatter(content)
        if not meta:
            return None, None

        try:
            data = SummaryData(
                student_name=meta.get("student_name", self._student_name),
                week_start=date.fromisoformat(meta["week_start"]),
                week_end=date.fromisoformat(meta["week_end"]),
                summary_text=body,
                messages_count=int(meta.get("messages_count", 0)),
                marks_count=int(meta.get("marks_count", 0)),
                week_type=meta.get("week_type", week_type),
                generated_at=datetime.fromisoformat(meta["generated_at"]),
            )
            return data, meta.get("prompt_hash")
        except (KeyError, ValueError) as err:
            _LOGGER.warning("Failed to parse summary %s: %s", path, err)
            return None, None

    def load_prepare(self, period: str) -> tuple[PrepareData | None, str | None]:
        """Load a cached preparation. Returns ``(data, prompt_hash)`` or ``(None, None)``."""
        path = self._dir / f"prepare_{period}.md"
        if not path.exists():
            return None, None

        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            return None, None

        meta, body = self._parse_frontmatter(content)
        if not meta:
            return None, None

        try:
            data = PrepareData(
                student_name=meta.get("student_name", self._student_name),
                target_date=date.fromisoformat(meta["target_date"]),
                preparation_text=body,
                lessons_count=int(meta.get("lessons_count", 0)),
                messages_count=int(meta.get("messages_count", 0)),
                period=meta.get("period", period),
                generated_at=datetime.fromisoformat(meta["generated_at"]),
            )
            return data, meta.get("prompt_hash")
        except (KeyError, ValueError) as err:
            _LOGGER.warning("Failed to parse prepare %s: %s", path, err)
            return None, None

    def load_all(self) -> dict[str, tuple[Any, str | None]]:
        """Load all cached summaries and preparations.

        Returns a dict like ``{"summary:current": (SummaryData, hash), ...}``.
        """
        results: dict[str, tuple[Any, str | None]] = {}

        if not self._dir.exists():
            return results

        for path in self._dir.glob("summary_*.md"):
            week_type = path.stem.removeprefix("summary_")
            data, prompt_hash = self.load_summary(week_type)
            if data is not None:
                results[f"summary:{week_type}"] = (data, prompt_hash)

        for path in self._dir.glob("prepare_*.md"):
            period = path.stem.removeprefix("prepare_")
            data, prompt_hash = self.load_prepare(period)
            if data is not None:
                results[f"prepare:{period}"] = (data, prompt_hash)

        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
        """Parse YAML-style frontmatter from content.

        Returns ``(metadata_dict, body_text)``.
        """
        parts = content.split("---", 2)
        if len(parts) < 3:
            return {}, content.strip()

        meta: dict[str, str] = {}
        for line in parts[1].strip().splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                meta[key.strip()] = val.strip().strip('"')

        body = parts[2].strip()
        return meta, body
