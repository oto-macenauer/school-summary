"""Pydantic models for YAML configuration."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from ..const import (
    DEFAULT_CANTEEN_UPDATE_INTERVAL,
    DEFAULT_GDRIVE_UPDATE_INTERVAL,
    DEFAULT_KOMENS_UPDATE_INTERVAL,
    DEFAULT_MARKS_UPDATE_INTERVAL,
    DEFAULT_PREPARE_UPDATE_INTERVAL,
    DEFAULT_SUMMARY_UPDATE_INTERVAL,
    DEFAULT_TIMETABLE_UPDATE_INTERVAL,
)

DEFAULT_SUMMARY_PROMPT = """\
Jsi školní asistent. Shrň hlavní události za {week_type} ({date_from} – {date_to}).
{student_info}
Zprávy z Komensu:
{messages}

Rozvrh:
{timetable}

Nové známky:
{marks}

Týdenní report z Google Drive:
{gdrive_report}

Vytvoř stručné shrnutí v češtině. Zaměř se na důležité události, testy, úkoly a změny v rozvrhu.\
"""

DEFAULT_SUMMARY_SYSTEM = """\
Jsi školní asistent pro českého studenta. Odpovídej vždy česky. \
Buď stručný a věcný. Zaměř se na praktické informace.\
"""

DEFAULT_PREPARE_TODAY_PROMPT = """\
Jsi školní asistent. Připrav přehled pro dnešní den {day_name} {target_date}.
{student_info}
Dnešní rozvrh:
{lessons}

Nedávné zprávy (posledních 14 dní):
{messages}

Shrň co je dnes důležité: jaké jsou hodiny, jestli jsou testy, \
co je potřeba mít s sebou, na co nezapomenout.\
"""

DEFAULT_PREPARE_TOMORROW_PROMPT = """\
Jsi školní asistent. Připrav přehled na zítřek {day_name} {target_date}.
{student_info}
Zítřejší rozvrh:
{lessons}

Nedávné zprávy (posledních 14 dní):
{messages}

Shrň co je potřeba připravit na zítra: jaké budou hodiny, \
jestli jsou testy, co zabalit, co se naučit, na co nezapomenout.\
"""

DEFAULT_PREPARE_SYSTEM = """\
Jsi školní asistent pro českého studenta. Odpovídej vždy česky. \
Buď stručný a praktický. Zaměř se na to, co student potřebuje vědět a připravit.\
"""


class ExtraSubject(BaseModel):
    """An extra subject or after-school activity."""

    name: str
    time: str  # e.g. "14:00"
    days: list[str] = Field(default_factory=list)  # e.g. ["po", "st"]


class StudentConfig(BaseModel):
    """Configuration for a single student."""

    name: str
    username: str
    password: str
    gdrive_folder_id: str = ""
    student_info: str = ""
    extra_subjects: list[ExtraSubject] = Field(default_factory=list)

    @field_validator("extra_subjects", mode="before")
    @classmethod
    def _coerce_extra_subjects(cls, v: object) -> object:
        if v is None:
            return []
        return v


class GDriveConfig(BaseModel):
    """Google Drive configuration."""

    service_account_path: str = ""
    reports_folder_id: str = ""
    school_year_start: str = ""


class CanteenConfig(BaseModel):
    """School canteen (Strava.cz) configuration."""

    cislo: str = ""
    s5url: str = ""
    lang: str = "CZ"


class UpdateIntervalsConfig(BaseModel):
    """Update interval configuration."""

    timetable: int = DEFAULT_TIMETABLE_UPDATE_INTERVAL
    marks: int = DEFAULT_MARKS_UPDATE_INTERVAL
    komens: int = DEFAULT_KOMENS_UPDATE_INTERVAL
    summary: int = DEFAULT_SUMMARY_UPDATE_INTERVAL
    prepare: int = DEFAULT_PREPARE_UPDATE_INTERVAL
    gdrive: int = DEFAULT_GDRIVE_UPDATE_INTERVAL
    canteen: int = DEFAULT_CANTEEN_UPDATE_INTERVAL


class PromptsConfig(BaseModel):
    """AI prompt templates configuration."""

    summary: str = DEFAULT_SUMMARY_PROMPT
    summary_system: str = DEFAULT_SUMMARY_SYSTEM
    prepare_today: str = DEFAULT_PREPARE_TODAY_PROMPT
    prepare_tomorrow: str = DEFAULT_PREPARE_TOMORROW_PROMPT
    prepare_system: str = DEFAULT_PREPARE_SYSTEM


class AppConfig(BaseModel):
    """Root application configuration."""

    base_url: str = ""
    students: list[StudentConfig] = Field(default_factory=list)
    gemini_api_key: str = ""
    gdrive: GDriveConfig = Field(default_factory=GDriveConfig)
    canteen: CanteenConfig = Field(default_factory=CanteenConfig)
    update_intervals: UpdateIntervalsConfig = Field(
        default_factory=UpdateIntervalsConfig
    )
    prompts: PromptsConfig = Field(default_factory=PromptsConfig)

    def masked(self) -> dict:
        """Return config dict with passwords and keys masked."""
        data = self.model_dump()
        for student in data.get("students", []):
            if student.get("password"):
                student["password"] = "***"
        if data.get("gemini_api_key"):
            data["gemini_api_key"] = data["gemini_api_key"][:8] + "***"
        return data
