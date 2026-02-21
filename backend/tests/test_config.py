"""Tests for configuration module."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from app.config import load_config, generate_default_config, get_config_path, _DEFAULT_CONFIG_YAML
from app.models.config import (
    AppConfig,
    GDriveConfig,
    PromptsConfig,
    StudentConfig,
    UpdateIntervalsConfig,
)
from app.const import (
    DEFAULT_KOMENS_UPDATE_INTERVAL,
    DEFAULT_MARKS_UPDATE_INTERVAL,
    DEFAULT_PREPARE_UPDATE_INTERVAL,
    DEFAULT_SUMMARY_UPDATE_INTERVAL,
    DEFAULT_TIMETABLE_UPDATE_INTERVAL,
)


class TestAppConfig:
    """Tests for AppConfig Pydantic model."""

    def test_app_config_defaults(self) -> None:
        """Test that AppConfig has correct defaults."""
        config = AppConfig()

        assert config.base_url == ""
        assert config.students == []
        assert config.gemini_api_key == ""
        assert config.gemini_model == "gemini-2.5-flash-lite"
        assert isinstance(config.gdrive, GDriveConfig)
        assert isinstance(config.update_intervals, UpdateIntervalsConfig)
        assert isinstance(config.prompts, PromptsConfig)

    def test_update_intervals_defaults(self) -> None:
        """Test that UpdateIntervalsConfig has correct defaults from const."""
        intervals = UpdateIntervalsConfig()

        assert intervals.timetable == DEFAULT_TIMETABLE_UPDATE_INTERVAL
        assert intervals.marks == DEFAULT_MARKS_UPDATE_INTERVAL
        assert intervals.komens == DEFAULT_KOMENS_UPDATE_INTERVAL
        assert intervals.summary == DEFAULT_SUMMARY_UPDATE_INTERVAL
        assert intervals.prepare == DEFAULT_PREPARE_UPDATE_INTERVAL

    def test_student_config(self) -> None:
        """Test creating a StudentConfig."""
        student = StudentConfig(
            name="Alice",
            username="alice",
            password="secret123",
        )
        assert student.name == "Alice"
        assert student.username == "alice"
        assert student.password == "secret123"

    def test_gdrive_config_defaults(self) -> None:
        """Test GDriveConfig defaults."""
        gdrive = GDriveConfig()
        assert gdrive.service_account_path == ""
        assert gdrive.reports_folder_id == ""
        assert gdrive.school_year_start == ""

    def test_prompts_config_defaults(self) -> None:
        """Test PromptsConfig has non-empty defaults."""
        prompts = PromptsConfig()
        assert len(prompts.summary) > 0
        assert len(prompts.summary_system) > 0
        assert len(prompts.prepare_today) > 0
        assert len(prompts.prepare_tomorrow) > 0
        assert len(prompts.prepare_system) > 0

    def test_app_config_masked(self) -> None:
        """Test that masked() hides sensitive data."""
        config = AppConfig(
            base_url="https://school.cz",
            students=[
                StudentConfig(
                    name="Alice",
                    username="alice",
                    password="my_secret_password",
                ),
            ],
            gemini_api_key="abcdefgh12345678",
        )

        masked = config.masked()

        assert masked["students"][0]["password"] == "***"
        assert masked["gemini_api_key"] == "abcdefgh***"
        # Non-sensitive data should not be masked
        assert masked["base_url"] == "https://school.cz"
        assert masked["students"][0]["name"] == "Alice"
        assert masked["students"][0]["username"] == "alice"

    def test_app_config_masked_empty_key(self) -> None:
        """Test that masked() handles empty gemini key."""
        config = AppConfig(gemini_api_key="")
        masked = config.masked()
        assert masked["gemini_api_key"] == ""

    def test_app_config_masked_short_key(self) -> None:
        """Test that masked() handles short gemini key."""
        config = AppConfig(gemini_api_key="short")
        masked = config.masked()
        # Short key still gets masked (first 8 chars + ***)
        assert masked["gemini_api_key"] == "short***"

    def test_app_config_masked_no_students(self) -> None:
        """Test that masked() works with no students."""
        config = AppConfig()
        masked = config.masked()
        assert masked["students"] == []

    def test_app_config_from_dict(self) -> None:
        """Test creating AppConfig from dict (model_validate)."""
        data = {
            "base_url": "https://bakalari.school.cz",
            "students": [
                {
                    "name": "Bob",
                    "username": "bob",
                    "password": "password123",
                }
            ],
            "gemini_api_key": "test_key",
            "update_intervals": {
                "timetable": 7200,
                "marks": 3600,
            },
        }

        config = AppConfig.model_validate(data)

        assert config.base_url == "https://bakalari.school.cz"
        assert len(config.students) == 1
        assert config.students[0].name == "Bob"
        assert config.update_intervals.timetable == 7200
        assert config.update_intervals.marks == 3600
        # Defaults for unset values
        assert config.update_intervals.komens == DEFAULT_KOMENS_UPDATE_INTERVAL


class TestLoadConfig:
    """Tests for configuration loading."""

    def test_load_config_creates_default(self, tmp_path: Path) -> None:
        """Test that load_config creates default config when file doesn't exist."""
        config_dir = tmp_path / "app_data"

        with patch("app.config.APP_DATA_DIR", str(config_dir)):
            with patch("app.config.get_app_data_dir", return_value=config_dir):
                with patch("app.config.get_config_path", return_value=config_dir / "config.yaml"):
                    # Generate default config
                    generate_default_config()

                    assert (config_dir / "config.yaml").exists()

                    # Load and validate
                    config = load_config()
                    assert isinstance(config, AppConfig)

    def test_generate_default_config_does_not_overwrite(self, tmp_path: Path) -> None:
        """Test that generate_default_config does not overwrite existing file."""
        config_dir = tmp_path / "app_data"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.yaml"
        config_file.write_text("base_url: 'https://custom.school.cz'\n", encoding="utf-8")

        with patch("app.config.get_config_path", return_value=config_file):
            generate_default_config()

        content = config_file.read_text(encoding="utf-8")
        assert "custom.school.cz" in content

    def test_load_config_from_yaml(self, tmp_path: Path) -> None:
        """Test loading config from existing YAML file."""
        config_dir = tmp_path / "app_data"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.yaml"

        yaml_content = """
base_url: "https://bakalari.test-school.cz"
students:
  - name: "Test Student"
    username: "test_user"
    password: "test_pass"
gemini_api_key: "test_key_123"
update_intervals:
  timetable: 7200
"""
        config_file.write_text(yaml_content, encoding="utf-8")

        with patch("app.config.get_config_path", return_value=config_file):
            config = load_config()

        assert config.base_url == "https://bakalari.test-school.cz"
        assert len(config.students) == 1
        assert config.students[0].name == "Test Student"
        assert config.gemini_api_key == "test_key_123"
        assert config.update_intervals.timetable == 7200

    def test_default_config_yaml_is_valid(self, tmp_path: Path) -> None:
        """Test that the default config YAML template can be parsed."""
        import yaml

        data = yaml.safe_load(_DEFAULT_CONFIG_YAML)
        assert data is not None
        assert "base_url" in data
        assert "students" in data
        assert "gemini_api_key" in data
        assert "gemini_model" in data
        assert "update_intervals" in data
        assert "prompts" in data

        # Should be valid for AppConfig
        config = AppConfig.model_validate(data)
        assert isinstance(config, AppConfig)
        assert config.gemini_model == "gemini-2.5-flash-lite"

    def test_gemini_model_from_yaml(self, tmp_path: Path) -> None:
        """Test loading custom gemini_model from YAML."""
        config_dir = tmp_path / "app_data"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.yaml"

        yaml_content = """
base_url: "https://test.school.cz"
students: []
gemini_api_key: "key"
gemini_model: "gemini-2.0-flash"
"""
        config_file.write_text(yaml_content, encoding="utf-8")

        with patch("app.config.get_config_path", return_value=config_file):
            config = load_config()

        assert config.gemini_model == "gemini-2.0-flash"

    def test_gemini_model_defaults_when_missing(self, tmp_path: Path) -> None:
        """Test that gemini_model defaults when not in YAML."""
        config_dir = tmp_path / "app_data"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.yaml"

        yaml_content = """
base_url: "https://test.school.cz"
students: []
gemini_api_key: "key"
"""
        config_file.write_text(yaml_content, encoding="utf-8")

        with patch("app.config.get_config_path", return_value=config_file):
            config = load_config()

        assert config.gemini_model == "gemini-2.5-flash-lite"
