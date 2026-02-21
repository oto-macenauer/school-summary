"""Configuration loader for the Bakalari application."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml

from .models.config import AppConfig

_LOGGER = logging.getLogger("bakalari.config")

APP_DATA_DIR = os.environ.get("APP_DATA_DIR", "./app_data")

_DEFAULT_CONFIG_YAML = """\
base_url: "https://bakalari.your-school.cz"

students:
  - name: "Student Name"
    username: "username"
    password: "password"
    # student_info: "Třída 5.A, třídní učitelka Mgr. Nováková"
    # mail_folder_id: ""  # Google Drive folder ID with synced Gmail MD files
    extra_subjects:
      # - name: "Angličtina kroužek"
      #   time: "14:00"
      #   days: ["po", "st"]

gemini_api_key: ""
gemini_model: "gemini-2.5-flash-lite"

gdrive:
  service_account_path: ""
  reports_folder_id: ""
  school_year_start: ""

canteen:
  cislo: ""
  s5url: ""
  lang: "CZ"

update_intervals:
  timetable: 3600    # seconds
  marks: 1800
  komens: 900
  summary: 86400
  prepare: 3600
  canteen: 3600
  mail: 900

# ──────────────────────────────────────────────
# Prompt Templates
# ──────────────────────────────────────────────
# All AI prompts are defined here as templates.
# Available variables are listed in comments above each template.
# Templates use Python str.format_map() syntax: {variable_name}
#
# To customize AI behavior, edit the templates below directly.
# No separate "custom prompt" field — the template IS the prompt.

prompts:
  # ── Weekly Summary Prompt ──
  # Variables: {week_type}, {date_from}, {date_to}, {messages},
  #            {timetable}, {marks}, {gdrive_report}, {student_info}
  summary: |
    Jsi školní asistent. Shrň hlavní události za {week_type} ({date_from} – {date_to}).

    Zprávy z Komensu:
    {messages}

    Rozvrh:
    {timetable}

    Nové známky:
    {marks}

    Týdenní report z Google Drive:
    {gdrive_report}

    Vytvoř stručné shrnutí v češtině. Zaměř se na důležité události,
    testy, úkoly a změny v rozvrhu.

  # ── Weekly Summary System Instruction ──
  summary_system: |
    Jsi školní asistent pro českého studenta. Odpovídej vždy česky.
    Buď stručný a věcný. Zaměř se na praktické informace.

  # ── Today Preparation Prompt ──
  # Variables: {target_date}, {day_name}, {lessons}, {messages}, {student_info}
  prepare_today: |
    Jsi školní asistent. Připrav přehled pro dnešní den {day_name} {target_date}.

    Dnešní rozvrh:
    {lessons}

    Nedávné zprávy (posledních 14 dní):
    {messages}

    Shrň co je dnes důležité: jaké jsou hodiny, jestli jsou testy,
    co je potřeba mít s sebou, na co nezapomenout.

  # ── Tomorrow Preparation Prompt ──
  # Same variables as prepare_today (including {student_info}).
  prepare_tomorrow: |
    Jsi školní asistent. Připrav přehled na zítřek {day_name} {target_date}.

    Zítřejší rozvrh:
    {lessons}

    Nedávné zprávy (posledních 14 dní):
    {messages}

    Shrň co je potřeba připravit na zítra: jaké budou hodiny,
    jestli jsou testy, co zabalit, co se naučit, na co nezapomenout.

  # ── Preparation System Instruction ──
  prepare_system: |
    Jsi školní asistent pro českého studenta. Odpovídej vždy česky.
    Buď stručný a praktický. Zaměř se na to, co student potřebuje vědět a připravit.
"""


def get_app_data_dir() -> Path:
    """Get the app data directory path."""
    return Path(APP_DATA_DIR)


def get_config_path() -> Path:
    """Get the configuration file path."""
    return get_app_data_dir() / "config.yaml"


def generate_default_config() -> None:
    """Generate a default config.yaml if it doesn't exist."""
    config_path = get_config_path()
    if config_path.exists():
        return

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(_DEFAULT_CONFIG_YAML, encoding="utf-8")
    _LOGGER.info("Generated default config at %s", config_path)


def load_config() -> AppConfig:
    """Load configuration from YAML file.

    Returns:
        Validated AppConfig instance
    """
    config_path = get_config_path()

    if not config_path.exists():
        generate_default_config()

    raw = config_path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw) or {}
    config = AppConfig.model_validate(data)
    _LOGGER.info("Loaded configuration from %s", config_path)
    return config
