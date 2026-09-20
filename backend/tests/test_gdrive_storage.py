"""Tests for GDriveStorage — per-school-year report layout and migration."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from app.core.gdrive import (
    WeeklyReport,
    current_school_year,
    school_year_label,
    school_year_slug,
)
from app.storage.gdrive_storage import GDriveStorage


def make_report(
    week: int, content: str = "Body", school_year: str = "", fetched: datetime | None = None,
) -> WeeklyReport:
    return WeeklyReport(
        week_number=week,
        content=content,
        file_name=f"Week {week}.docx",
        fetched_at=fetched or datetime(2026, 9, 15, 8, 0, 0),
        school_year=school_year,
    )


@pytest.fixture
def storage(tmp_path) -> GDriveStorage:
    return GDriveStorage(tmp_path / "gdrive", "Alice")


class TestSchoolYearHelpers:
    """Tests for the school year label/slug helpers."""

    def test_label(self):
        assert school_year_label(date(2026, 9, 1)) == "2026/2027"

    def test_slug(self):
        assert school_year_slug("2026/2027") == "2026-2027"

    def test_slug_is_idempotent(self):
        assert school_year_slug("2026-2027") == "2026-2027"

    def test_current_school_year_matches_label(self):
        assert current_school_year() == school_year_label(
            date(date.today().year if date.today().month >= 9
                 else date.today().year - 1, 9, 1),
        )


class TestPerYearLayout:
    """Reports are filed under their school year."""

    def test_saves_into_year_folder(self, storage):
        path = storage.save_report(make_report(1, school_year="2026/2027"))
        assert path.parent.name == "2026-2027"
        assert path.name == "week_01.md"

    def test_writes_school_year_and_report_id(self, storage):
        path = storage.save_report(make_report(3, school_year="2026/2027"))
        raw = path.read_text(encoding="utf-8")
        assert "school_year: 2026/2027" in raw
        assert "report_id: 2026-2027-week-03" in raw

    def test_report_id_is_year_scoped(self):
        assert GDriveStorage.report_id(1, "2025/2026") == "2025-2026-week-01"
        assert GDriveStorage.report_id(1, "2026/2027") == "2026-2027-week-01"

    def test_same_week_in_two_years_coexists(self, storage):
        storage.save_report(make_report(1, "Old year.", "2025/2026"))
        storage.save_report(make_report(1, "New year.", "2026/2027"))

        assert storage.get_report(1, "2025/2026") == "Old year."
        assert storage.get_report(1, "2026/2027") == "New year."
        assert len(storage.get_all_reports()) == 2

    def test_exists_is_year_scoped(self, storage):
        """The regression: last year's week 1 must not mask the new year's."""
        storage.save_report(make_report(1, "Old year.", "2025/2026"))

        assert storage.report_exists(1, "2025/2026")
        assert not storage.report_exists(1, "2026/2027")

    def test_defaults_to_current_school_year(self, storage):
        storage.save_report(make_report(2))
        assert storage.report_exists(2, current_school_year())
        assert storage.get_report(2) == "Body"

    def test_report_school_year_wins_over_argument(self, storage):
        path = storage.save_report(
            make_report(5, school_year="2026/2027"), school_year="2019/2020",
        )
        assert path.parent.name == "2026-2027"

    def test_missing_report_returns_none(self, storage):
        assert storage.get_report(9, "2026/2027") is None

    def test_no_reports_at_all(self, storage):
        assert storage.get_all_reports() == []
        assert storage.get_latest_report() is None
        assert storage.get_all_reports_data() == []


class TestOrdering:
    """Latest report is the newest week of the newest school year."""

    def test_latest_crosses_year_boundary(self, storage):
        storage.save_report(make_report(42, "Old week 42.", "2025/2026"))
        storage.save_report(make_report(2, "New week 2.", "2026/2027"))

        assert storage.get_latest_report() == "New week 2."

    def test_all_reports_sorted_oldest_first(self, storage):
        storage.save_report(make_report(2, school_year="2026/2027"))
        storage.save_report(make_report(42, school_year="2025/2026"))
        storage.save_report(make_report(1, school_year="2026/2027"))

        stems = [(p.parent.name, p.stem) for p in storage.get_all_reports()]
        assert stems == [
            ("2025-2026", "week_42"),
            ("2026-2027", "week_01"),
            ("2026-2027", "week_02"),
        ]

    def test_reports_data_newest_first(self, storage):
        storage.save_report(make_report(42, "Old", "2025/2026"))
        storage.save_report(make_report(1, "New", "2026/2027"))

        data = storage.get_all_reports_data()
        assert [(r["school_year"], r["week_number"]) for r in data] == [
            ("2026/2027", 1),
            ("2025/2026", 42),
        ]
        assert data[0]["report_id"] == "2026-2027-week-01"

    def test_find_report_prefers_newest_year(self, storage):
        storage.save_report(make_report(1, "Old year.", "2025/2026"))
        storage.save_report(make_report(1, "New year.", "2026/2027"))

        assert storage.find_report(1) == "New year."

    def test_find_report_falls_back_to_older_year(self, storage):
        storage.save_report(make_report(37, "Only old.", "2025/2026"))

        assert storage.find_report(37) == "Only old."
        assert storage.find_report(99) is None


class TestLegacyMigration:
    """Flat week_NN.md reports are filed into their school year."""

    def _write_legacy(self, storage, week: int, school_year: str, body: str = "Legacy body.") -> None:
        storage.ensure_directory()
        path = storage.storage_path / f"week_{week:02d}.md"
        path.write_text(
            "\n".join([
                "---",
                f"week_number: {week}",
                f"school_year: {school_year}",
                'fetched_at: "2026-02-10T17:11:24.048119"',
                'source_file: "Week 1.docx"',
                "---",
                "",
                body,
            ]),
            encoding="utf-8",
        )

    def test_moves_flat_files_into_year_folder(self, storage):
        self._write_legacy(storage, 1, "2025/2026")
        self._write_legacy(storage, 42, "2025/2026")

        assert storage.migrate_legacy_layout() == 2

        assert not list(storage.storage_path.glob("week_*.md"))
        assert storage.report_exists(1, "2025/2026")
        assert storage.get_report(42, "2025/2026") == "Legacy body."

    def test_migration_unblocks_the_new_year(self, storage):
        self._write_legacy(storage, 1, "2025/2026")
        storage.migrate_legacy_layout()

        assert not storage.report_exists(1, "2026/2027")
        storage.save_report(make_report(1, "Fresh", "2026/2027"))
        assert storage.get_report(1, "2026/2027") == "Fresh"
        assert storage.get_report(1, "2025/2026") == "Legacy body."

    def test_falls_back_to_fetched_at(self, storage):
        storage.ensure_directory()
        path = storage.storage_path / "week_05.md"
        path.write_text(
            "\n".join([
                "---",
                "week_number: 5",
                'fetched_at: "2025-10-06T10:00:00"',
                "---",
                "",
                "No school year.",
            ]),
            encoding="utf-8",
        )

        assert storage.migrate_legacy_layout() == 1
        assert storage.get_report(5, "2025/2026") == "No school year."

    def test_is_idempotent(self, storage):
        self._write_legacy(storage, 1, "2025/2026")

        assert storage.migrate_legacy_layout() == 1
        assert storage.migrate_legacy_layout() == 0

    def test_keeps_file_when_target_exists(self, storage):
        self._write_legacy(storage, 1, "2025/2026")
        storage.save_report(make_report(1, "Already there.", "2025/2026"))

        assert storage.migrate_legacy_layout() == 0
        assert (storage.storage_path / "week_01.md").exists()
        assert storage.get_report(1, "2025/2026") == "Already there."

    def test_no_student_directory(self, storage):
        assert storage.migrate_legacy_layout() == 0

    def test_unmigrated_files_are_still_listed(self, storage):
        """A flat file left behind stays readable until it is migrated."""
        self._write_legacy(storage, 7, "2025/2026")

        assert len(storage.get_all_reports()) == 1
        assert storage.get_all_reports_data()[0]["week_number"] == 7


class TestUntaggedFiles:
    """Tagging picks up reports across school years."""

    def test_untagged_spans_years(self, storage):
        storage.save_report(make_report(42, school_year="2025/2026"))
        storage.save_report(make_report(1, school_year="2026/2027"))

        untagged = storage.get_untagged_files()
        assert len(untagged) == 2

    def test_tagged_file_excluded(self, storage):
        path = storage.save_report(make_report(1, school_year="2026/2027"))
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "week_number: 1", "week_number: 1\ntagged_at: 2026-09-15",
            ),
            encoding="utf-8",
        )

        assert storage.get_untagged_files() == []
