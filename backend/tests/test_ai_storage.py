"""Tests for AIStorage persistence module."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from app.modules.prepare import PrepareData
from app.modules.summary import SummaryData
from app.storage.ai_storage import AIStorage


@pytest.fixture
def ai_storage(tmp_path, monkeypatch) -> AIStorage:
    """Create an AIStorage pointing at a temporary directory."""
    monkeypatch.setattr("app.storage.ai_storage.get_app_data_dir", lambda: tmp_path)
    return AIStorage("TestStudent")


@pytest.fixture
def sample_summary() -> SummaryData:
    return SummaryData(
        student_name="TestStudent",
        week_start=date(2026, 3, 2),
        week_end=date(2026, 3, 8),
        summary_text="This is the weekly summary.\n\nIt has multiple lines.",
        messages_count=5,
        marks_count=2,
        week_type="current",
        generated_at=datetime(2026, 3, 8, 14, 0, 0),
    )


@pytest.fixture
def sample_prepare() -> PrepareData:
    return PrepareData(
        student_name="TestStudent",
        target_date=date(2026, 3, 9),
        preparation_text="Prepare your homework.\n\nBring gym clothes.",
        lessons_count=6,
        messages_count=3,
        period="tomorrow",
        generated_at=datetime(2026, 3, 8, 14, 0, 0),
    )


class TestSaveLoadSummary:
    """Tests for summary save/load roundtrip."""

    def test_save_load_summary_roundtrip(self, ai_storage, sample_summary):
        """Save a SummaryData and load it back — all fields must match."""
        prompt_hash = "abc123def456"
        ai_storage.save_summary(sample_summary, prompt_hash)

        loaded, loaded_hash = ai_storage.load_summary("current")

        assert loaded is not None
        assert loaded.student_name == sample_summary.student_name
        assert loaded.week_start == sample_summary.week_start
        assert loaded.week_end == sample_summary.week_end
        assert loaded.summary_text == sample_summary.summary_text
        assert loaded.messages_count == sample_summary.messages_count
        assert loaded.marks_count == sample_summary.marks_count
        assert loaded.week_type == sample_summary.week_type
        assert loaded.generated_at == sample_summary.generated_at
        assert loaded_hash == prompt_hash

    def test_save_overwrites_summary(self, ai_storage, sample_summary):
        """Saving twice with same week_type overwrites the file."""
        ai_storage.save_summary(sample_summary, "hash1")

        updated = SummaryData(
            student_name="TestStudent",
            week_start=date(2026, 3, 2),
            week_end=date(2026, 3, 8),
            summary_text="Updated summary text.",
            messages_count=10,
            marks_count=5,
            week_type="current",
            generated_at=datetime(2026, 3, 8, 15, 0, 0),
        )
        ai_storage.save_summary(updated, "hash2")

        loaded, loaded_hash = ai_storage.load_summary("current")
        assert loaded is not None
        assert loaded.summary_text == "Updated summary text."
        assert loaded.messages_count == 10
        assert loaded_hash == "hash2"


class TestSaveLoadPrepare:
    """Tests for preparation save/load roundtrip."""

    def test_save_load_prepare_roundtrip(self, ai_storage, sample_prepare):
        """Save a PrepareData and load it back — all fields must match."""
        prompt_hash = "f6e5d4c3b2a1"
        ai_storage.save_prepare(sample_prepare, prompt_hash)

        loaded, loaded_hash = ai_storage.load_prepare("tomorrow")

        assert loaded is not None
        assert loaded.student_name == sample_prepare.student_name
        assert loaded.target_date == sample_prepare.target_date
        assert loaded.preparation_text == sample_prepare.preparation_text
        assert loaded.lessons_count == sample_prepare.lessons_count
        assert loaded.messages_count == sample_prepare.messages_count
        assert loaded.period == sample_prepare.period
        assert loaded.generated_at == sample_prepare.generated_at
        assert loaded_hash == prompt_hash

    def test_save_overwrites_prepare(self, ai_storage, sample_prepare):
        """Saving twice with same period overwrites the file."""
        ai_storage.save_prepare(sample_prepare, "hash1")

        updated = PrepareData(
            student_name="TestStudent",
            target_date=date(2026, 3, 9),
            preparation_text="New prep text.",
            lessons_count=4,
            messages_count=1,
            period="tomorrow",
            generated_at=datetime(2026, 3, 8, 16, 0, 0),
        )
        ai_storage.save_prepare(updated, "hash2")

        loaded, loaded_hash = ai_storage.load_prepare("tomorrow")
        assert loaded is not None
        assert loaded.preparation_text == "New prep text."
        assert loaded_hash == "hash2"


class TestLoadNonexistent:
    """Tests for loading when no data exists."""

    def test_load_nonexistent_summary_returns_none(self, ai_storage):
        loaded, loaded_hash = ai_storage.load_summary("current")
        assert loaded is None
        assert loaded_hash is None

    def test_load_nonexistent_prepare_returns_none(self, ai_storage):
        loaded, loaded_hash = ai_storage.load_prepare("today")
        assert loaded is None
        assert loaded_hash is None


class TestLoadAll:
    """Tests for load_all aggregation."""

    def test_load_all_returns_all_saved(self, ai_storage):
        """Save multiple items, verify load_all returns all of them."""
        now = datetime(2026, 3, 8, 14, 0, 0)

        for wt in ("last", "current", "next"):
            s = SummaryData(
                student_name="TestStudent",
                week_start=date(2026, 3, 2),
                week_end=date(2026, 3, 8),
                summary_text=f"Summary {wt}",
                messages_count=1,
                marks_count=1,
                week_type=wt,
                generated_at=now,
            )
            ai_storage.save_summary(s, f"shash_{wt}")

        for period in ("today", "tomorrow"):
            p = PrepareData(
                student_name="TestStudent",
                target_date=date(2026, 3, 9),
                preparation_text=f"Prepare {period}",
                lessons_count=3,
                messages_count=2,
                period=period,
                generated_at=now,
            )
            ai_storage.save_prepare(p, f"phash_{period}")

        result = ai_storage.load_all()
        assert len(result) == 5

        assert "summary:last" in result
        assert "summary:current" in result
        assert "summary:next" in result
        assert "prepare:today" in result
        assert "prepare:tomorrow" in result

        data, h = result["summary:current"]
        assert data.summary_text == "Summary current"
        assert h == "shash_current"

        data, h = result["prepare:today"]
        assert data.preparation_text == "Prepare today"
        assert h == "phash_today"

    def test_load_all_empty_directory(self, ai_storage):
        """load_all returns empty dict when no files exist."""
        result = ai_storage.load_all()
        assert result == {}


class TestPromptHash:
    """Tests for prompt hash round-trip."""

    def test_prompt_hash_stored_and_returned(self, ai_storage, sample_summary):
        expected_hash = "a1b2c3d4e5f67890abcdef"
        ai_storage.save_summary(sample_summary, expected_hash)
        _, loaded_hash = ai_storage.load_summary("current")
        assert loaded_hash == expected_hash


class TestEnsureDirectory:
    """Tests for directory creation."""

    def test_ensure_directory_creates_path(self, ai_storage):
        assert not ai_storage.storage_path.exists()
        ai_storage.ensure_directory()
        assert ai_storage.storage_path.exists()
        assert ai_storage.storage_path.is_dir()

    def test_ensure_directory_idempotent(self, ai_storage):
        ai_storage.ensure_directory()
        ai_storage.ensure_directory()
        assert ai_storage.storage_path.exists()
