"""Storage module for saving Google Drive weekly reports to Markdown files.

Reports are filed per school year (``<student>/2026-2027/week_03.md``) because
week numbers restart at 1 every September.  A flat ``week_NN.md`` layout made
the new year's week 1 look like it was already stored, so the sync skipped
every report of the new year.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from ..core.gdrive import (
    WeeklyReport,
    current_school_year,
    get_school_year_start,
    school_year_label,
    school_year_slug,
)

_LOGGER = logging.getLogger("bakalari.gdrive_storage")

_YEAR_DIR_PATTERN = re.compile(r"^\d{4}-\d{4}$")
_WEEK_FILE_PATTERN = re.compile(r"^week_(\d+)$")


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

    # ── paths and identity ────────────────────────────────────────────────

    def _resolve_year(self, school_year: str | None) -> str:
        return school_year.strip() if school_year else current_school_year()

    def _year_path(self, school_year: str | None = None) -> Path:
        return self._student_path / school_year_slug(self._resolve_year(school_year))

    def _report_path(self, week_number: int, school_year: str | None = None) -> Path:
        return self._year_path(school_year) / f"week_{week_number:02d}.md"

    @staticmethod
    def report_id(week_number: int, school_year: str) -> str:
        """Stable cross-year identity of a report, e.g. ``2026-2027-week-03``."""
        return f"{school_year_slug(school_year)}-week-{week_number:02d}"

    def report_exists(self, week_number: int, school_year: str | None = None) -> bool:
        return self._report_path(week_number, school_year).exists()

    # ── writing ───────────────────────────────────────────────────────────

    def save_report(self, report: WeeklyReport, school_year: str = "") -> Path:
        """Save a weekly report as a Markdown file with YAML frontmatter."""
        year = self._resolve_year(report.school_year or school_year)
        path = self._report_path(report.week_number, year)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Convert plain text content to markdown
        md_content = self._convert_to_markdown(report.content)

        metadata = [
            "---",
            f"report_id: {self.report_id(report.week_number, year)}",
            f"week_number: {report.week_number}",
            f"school_year: {year}",
            f"fetched_at: \"{report.fetched_at.isoformat()}\"",
            f"source_file: \"{report.file_name}\"",
            "---",
            "",
        ]

        full_content = "\n".join(metadata) + md_content

        try:
            path.write_text(full_content, encoding="utf-8")
            _LOGGER.info(
                "Saved GDrive report %s week %d: %s", year, report.week_number, path,
            )
            return path
        except OSError as err:
            _LOGGER.error("Failed to save GDrive report: %s", err)
            raise

    # ── reading ───────────────────────────────────────────────────────────

    def get_report(self, week_number: int, school_year: str | None = None) -> str | None:
        """Text of a stored report (without frontmatter) for one school year."""
        path = self._report_path(week_number, school_year)
        if not path.exists():
            return None
        return self._body(path)

    def find_report(self, week_number: int) -> str | None:
        """Text of a week's report, preferring the most recent school year."""
        for path in reversed(self.get_all_reports()):
            if self._week_of(path) == week_number:
                return self._body(path)
        return None

    def get_latest_report(self) -> str | None:
        """Content of the most recent report by school year, then week number."""
        reports = self.get_all_reports()
        if not reports:
            return None
        return self._body(reports[-1])

    def get_all_reports(self) -> list[Path]:
        """Every stored report across all school years, oldest first."""
        if not self._student_path.exists():
            return []
        paths = list(self._student_path.glob("*/week_*.md"))
        # Reports written before the per-year layout may still sit flat.
        paths.extend(self._student_path.glob("week_*.md"))
        return sorted(paths, key=self._sort_key)

    def get_untagged_files(self) -> list[Path]:
        """Return report files that have not been tagged yet."""
        return [
            f for f in self.get_all_reports()
            if "tagged_at:" not in f.read_text(encoding="utf-8")
        ]

    def get_all_reports_data(self) -> list[dict[str, Any]]:
        """Get all reports with parsed metadata and content, newest first."""
        reports: list[dict[str, Any]] = []
        for path in self.get_all_reports():
            try:
                meta = self._meta(path)
                week_number = int(meta.get("week_number") or self._week_of(path) or 0)
                school_year = meta.get("school_year") or self._year_of(path)
                reports.append({
                    "report_id": meta.get("report_id")
                    or self.report_id(week_number, school_year),
                    "week_number": week_number,
                    "school_year": school_year,
                    "fetched_at": meta.get("fetched_at", ""),
                    "source_file": meta.get("source_file", ""),
                    "content": self._body(path),
                })
            except Exception as err:
                _LOGGER.warning("Failed to parse report %s: %s", path, err)
        reports.sort(
            key=lambda r: (r["school_year"], r["week_number"]), reverse=True,
        )
        return reports

    # ── migration ─────────────────────────────────────────────────────────

    def migrate_legacy_layout(self) -> int:
        """Move flat ``week_NN.md`` reports into their school-year subfolder.

        Each legacy file records its school year in frontmatter, which is
        enough to file it correctly; ``fetched_at`` is the fallback.  Returns
        the number of files moved.
        """
        if not self._student_path.exists():
            return 0

        moved = 0
        for path in sorted(self._student_path.glob("week_*.md")):
            week_number = self._week_of(path)
            if week_number is None:
                continue
            year = self._legacy_year(path)
            target = self._report_path(week_number, year)
            if target.exists():
                _LOGGER.warning(
                    "Skipping legacy report %s: %s already exists", path, target,
                )
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            path.rename(target)
            moved += 1

        if moved:
            _LOGGER.info(
                "Migrated %d GDrive reports of %s into per-year folders",
                moved, self._student_name,
            )
        return moved

    def _legacy_year(self, path: Path) -> str:
        """School year of a report stored before the per-year layout."""
        meta = self._meta(path)
        year = meta.get("school_year", "").strip()
        if _YEAR_DIR_PATTERN.match(school_year_slug(year)):
            return year

        fetched_at = meta.get("fetched_at", "")
        if fetched_at:
            try:
                fetched = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
                # A report is fetched during its own school year, so the fetch
                # date identifies the year the file belongs to.
                return school_year_label(get_school_year_start(fetched.date()))
            except ValueError:
                pass
        return current_school_year()

    # ── helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _week_of(path: Path) -> int | None:
        match = _WEEK_FILE_PATTERN.match(path.stem)
        return int(match.group(1)) if match else None

    def _year_of(self, path: Path) -> str:
        """School year a stored path belongs to, from its parent folder."""
        parent = path.parent.name
        if _YEAR_DIR_PATTERN.match(parent):
            return parent.replace("-", "/")
        return ""

    def _sort_key(self, path: Path) -> tuple[str, int]:
        return (self._year_of(path), self._week_of(path) or 0)

    @staticmethod
    def _meta(path: Path) -> dict[str, str]:
        """Parse the YAML frontmatter of a report file."""
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            return {}
        parts = raw.split("---", 2)
        if len(parts) < 3:
            return {}
        meta: dict[str, str] = {}
        for line in parts[1].strip().splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                meta[key.strip()] = val.strip().strip('"')
        return meta

    @staticmethod
    def _body(path: Path) -> str:
        """Report text with the YAML frontmatter stripped."""
        content = path.read_text(encoding="utf-8")
        parts = content.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
        return content.strip()

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
