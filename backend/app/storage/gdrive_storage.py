"""Storage module for saving Google Drive weekly reports to Markdown files."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from ..core.gdrive import WeeklyReport

_LOGGER = logging.getLogger("bakalari.gdrive_storage")


class GDriveStorage:
    """Handles storage of weekly reports as Markdown files."""

    def __init__(self, storage_path: str | Path, student_name: str) -> None:
        self._base_path = Path(storage_path)
        self._student_name = re.sub(r'[<>:"/\\|?*]', "_", student_name).strip(". ") or "default"
        self._student_path = self._base_path / self._student_name

    @property
    def storage_path(self) -> Path:
        return self._student_path

    def ensure_directory(self) -> None:
        self._student_path.mkdir(parents=True, exist_ok=True)

    def _report_path(self, week_number: int) -> Path:
        return self._student_path / f"week_{week_number:02d}.md"

    def report_exists(self, week_number: int) -> bool:
        return self._report_path(week_number).exists()

    def save_report(self, report: WeeklyReport, school_year: str = "") -> Path:
        """Save a weekly report as a Markdown file with YAML frontmatter."""
        self.ensure_directory()
        path = self._report_path(report.week_number)

        # Convert plain text content to markdown
        md_content = self._convert_to_markdown(report.content)

        metadata = [
            "---",
            f"week_number: {report.week_number}",
            f"school_year: {school_year}",
            f"fetched_at: \"{report.fetched_at.isoformat()}\"",
            f"source_file: \"{report.file_name}\"",
            "---",
            "",
        ]

        full_content = "\n".join(metadata) + md_content

        try:
            path.write_text(full_content, encoding="utf-8")
            _LOGGER.info("Saved GDrive report week %d: %s", report.week_number, path)
            return path
        except OSError as err:
            _LOGGER.error("Failed to save GDrive report: %s", err)
            raise

    def get_report(self, week_number: int) -> str | None:
        """Get the text content of a stored report (without frontmatter)."""
        path = self._report_path(week_number)
        if not path.exists():
            return None
        content = path.read_text(encoding="utf-8")
        # Strip YAML frontmatter
        parts = content.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
        return content.strip()

    def get_latest_report(self) -> str | None:
        """Get the content of the most recent report by week number."""
        reports = self.get_all_reports()
        if not reports:
            return None
        # Sort by filename (week_NN.md) descending
        reports.sort(reverse=True)
        content = reports[0].read_text(encoding="utf-8")
        parts = content.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
        return content.strip()

    def get_all_reports(self) -> list[Path]:
        if not self._student_path.exists():
            return []
        return sorted(self._student_path.glob("week_*.md"))

    def get_all_reports_data(self) -> list[dict[str, Any]]:
        """Get all reports with parsed metadata and content."""
        reports: list[dict[str, Any]] = []
        for path in self.get_all_reports():
            try:
                raw = path.read_text(encoding="utf-8")
                parts = raw.split("---", 2)
                meta: dict[str, Any] = {}
                content = raw.strip()
                if len(parts) >= 3:
                    for line in parts[1].strip().splitlines():
                        if ":" in line:
                            key, val = line.split(":", 1)
                            meta[key.strip()] = val.strip().strip('"')
                    content = parts[2].strip()
                reports.append({
                    "week_number": int(meta.get("week_number", 0)),
                    "school_year": meta.get("school_year", ""),
                    "fetched_at": meta.get("fetched_at", ""),
                    "source_file": meta.get("source_file", ""),
                    "content": content,
                })
            except Exception as err:
                _LOGGER.warning("Failed to parse report %s: %s", path, err)
        reports.sort(key=lambda r: r["week_number"], reverse=True)
        return reports

    def _convert_to_markdown(self, text: str) -> str:
        """Convert plain text to markdown, detecting section headers."""
        lines = text.split("\n")
        result: list[str] = []
        for line in lines:
            stripped = line.strip()
            # Detect all-caps section headers (e.g., ENGLISH, HOMEWORK, NEXT WEEK PLAN)
            if (
                stripped
                and stripped == stripped.upper()
                and len(stripped) > 2
                and stripped.isalpha() or " " in stripped and all(
                    w.isalpha() or w == "" for w in stripped.split()
                )
            ):
                # Check it's a real header, not just a short word
                if len(stripped) >= 3 and not stripped.isdigit():
                    result.append(f"\n## {stripped}\n")
                    continue
            result.append(line)
        return "\n".join(result)
