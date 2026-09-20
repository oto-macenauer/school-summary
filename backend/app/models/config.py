"""Pydantic models for YAML configuration."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from ..const import (
    DEFAULT_AGENDA_DIGEST_INTERVAL,
    DEFAULT_AGENDA_BACKFILL_DAYS,
    DEFAULT_AGENDA_FUTURE_WINDOW_DAYS,
    DEFAULT_AGENDA_PAST_WINDOW_DAYS,
    DEFAULT_AGENDA_REMINDER_HOUR,
    DEFAULT_AGENDA_TASK_LOOKAHEAD_DAYS,
    DEFAULT_CANTEEN_UPDATE_INTERVAL,
    DEFAULT_GDRIVE_UPDATE_INTERVAL,
    DEFAULT_KOMENS_UPDATE_INTERVAL,
    DEFAULT_MAIL_UPDATE_INTERVAL,
    DEFAULT_MARKS_UPDATE_INTERVAL,
    DEFAULT_PREPARE_UPDATE_INTERVAL,
    DEFAULT_SUMMARY_UPDATE_INTERVAL,
    DEFAULT_TAGGING_UPDATE_INTERVAL,
    DEFAULT_TIMETABLE_UPDATE_INTERVAL,
)

DEFAULT_SUMMARY_PROMPT = """\
Jsi školní asistent. Shrň hlavní události za {week_type} ({date_from} – {date_to}).
{student_info}
Zprávy z Komensu:
{messages}

Rozvrh:
{timetable}

Probraná látka (zápisy učitelů):
{lesson_notes}

Nové známky:
{marks}

Týdenní report z Google Drive:
{gdrive_report}

Vytvoř stručné shrnutí v češtině. Zaměř se na důležité události, testy, úkoly, změny v rozvrhu a na to, co se ve škole probíralo.\
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


# The tagging prompt is filled by plain substitution of {today} and {messages},
# never str.format — it contains a JSON schema full of braces.
DEFAULT_TAGGING_PROMPT = """\
Analyzuj následující školní zprávy. Dnešní datum je {today}.

Pro každou zprávu urči:
1. temporal - data nebo rozsahy dat, ke kterým se zpráva vztahuje.
   Relativní data (příští pondělí, za týden) vyřeš vzhledem k datu odeslání zprávy.
   Každá zpráva musí mít alespoň 1 temporal tag (fallback: datum odeslání).
2. subjects - školní předměty zmíněné ve zprávě (česky: Matematika, Fyzika, ...).
3. importance - kategorie z: test, homework, trip, event, absence,
   schedule_change, important, info
4. events - konkrétní akce s datem, které patří do kalendáře: písemky, zkoušky,
   výlety, exkurze, třídní schůzky, besídky, ředitelské volno, uzávěrky.
   kind musí být jeden z: test, exam, homework, trip, event, meeting, holiday, deadline.
   Uveď date (YYYY-MM-DD), volitelně date_to u vícedenních akcí, time_from (HH:MM),
   subject a location. Událost nevytvářej, pokud zpráva neuvádí datum.
5. tasks - co je potřeba udělat, zaplatit, přinést, koupit, podepsat nebo vrátit.
   kind musí být jeden z: pay, bring, prepare, buy, sign, return, other.
   U plateb uveď amount (číslo) a currency (CZK). due je termín (YYYY-MM-DD),
   pokud je ve zprávě uveden.

Zprávy:

{messages}

Odpověz POUZE validním JSON objektem, klíčem je pořadové číslo zprávy:
{"1": {"temporal": [{"from": "2026-10-14", "to": null, "label": "písemka"}],
       "subjects": ["Matematika"],
       "importance": ["test"],
       "events": [{"kind": "test", "title": "Písemka z rovnic", "date": "2026-10-14",
                   "date_to": null, "time_from": "08:00", "subject": "Matematika",
                   "location": null}],
       "tasks": [{"kind": "pay", "title": "Záloha na lyžařský kurz", "due": "2026-10-10",
                  "amount": 3500, "currency": "CZK", "subject": null}]},
 "2": {...}}

Prázdné seznamy použij tam, kde zpráva nic takového neobsahuje.
Nevymýšlej si data, částky ani úkoly, které ve zprávě nejsou. Bez dalšího textu.\
"""

DEFAULT_TAGGING_SYSTEM = """\
Jsi školní asistent, který analyzuje zprávy a extrahuje z nich strukturovaná data. \
Odpovídej POUZE validním JSON. Žádný další text. \
Předměty i názvy událostí piš v češtině. Kategorie používej pouze z daných seznamů. \
Nikdy si nevymýšlej data, částky ani úkoly, které ve zprávě nejsou.\
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
    mail_folder_id: str = ""
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
    # Rollover anchor of the school year: only month/day are used, so the
    # value stays correct in later school years.
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
    mail: int = DEFAULT_MAIL_UPDATE_INTERVAL
    tagging: int = DEFAULT_TAGGING_UPDATE_INTERVAL
    agenda_digest: int = DEFAULT_AGENDA_DIGEST_INTERVAL


class AgendaConfig(BaseModel):
    """Calendar and checklist behaviour."""

    # How far back message history is re-processed when the extraction schema
    # changes. Older messages keep their existing tags and stay out of the
    # calendar.
    backfill_days: int = DEFAULT_AGENDA_BACKFILL_DAYS
    # Rolling window the calendar shows by default.
    past_window_days: int = DEFAULT_AGENDA_PAST_WINDOW_DAYS
    future_window_days: int = DEFAULT_AGENDA_FUTURE_WINDOW_DAYS
    # Day-before push digest.
    reminder_enabled: bool = True
    reminder_hour: int = DEFAULT_AGENDA_REMINDER_HOUR
    reminder_task_days: int = DEFAULT_AGENDA_TASK_LOOKAHEAD_DAYS

    @field_validator("reminder_hour")
    @classmethod
    def _clamp_hour(cls, v: int) -> int:
        return min(max(v, 0), 23)

    @field_validator(
        "backfill_days",
        "past_window_days",
        "future_window_days",
        "reminder_task_days",
    )
    @classmethod
    def _non_negative(cls, v: int) -> int:
        return max(v, 0)


class PromptsConfig(BaseModel):
    """AI prompt templates configuration."""

    summary: str = DEFAULT_SUMMARY_PROMPT
    summary_system: str = DEFAULT_SUMMARY_SYSTEM
    prepare_today: str = DEFAULT_PREPARE_TODAY_PROMPT
    prepare_tomorrow: str = DEFAULT_PREPARE_TOMORROW_PROMPT
    prepare_system: str = DEFAULT_PREPARE_SYSTEM
    tagging: str = DEFAULT_TAGGING_PROMPT
    tagging_system: str = DEFAULT_TAGGING_SYSTEM


class AppConfig(BaseModel):
    """Root application configuration."""

    base_url: str = ""
    students: list[StudentConfig] = Field(default_factory=list)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash-lite"
    gdrive: GDriveConfig = Field(default_factory=GDriveConfig)
    canteen: CanteenConfig = Field(default_factory=CanteenConfig)
    update_intervals: UpdateIntervalsConfig = Field(
        default_factory=UpdateIntervalsConfig
    )
    agenda: AgendaConfig = Field(default_factory=AgendaConfig)
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
