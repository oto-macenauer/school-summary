"""Manages per-student API clients and cached data."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import aiohttp

from ..config import get_app_data_dir
from ..core.client import BakalariClient
from ..core.gdrive import GoogleDriveClient
from ..core.gemini import GeminiClient
from ..models.config import AppConfig, StudentConfig
from ..modules.canteen import CanteenData, CanteenModule
from ..modules.komens import KomensModule, MessagesData
from ..modules.marks import MarksData, MarksModule
from ..modules.prepare import PrepareData, PrepareModule, get_next_school_day, get_tomorrow
from ..modules.summary import SummaryData, SummaryModule
from ..modules.timetable import TimetableModule, WeekTimetable
from ..storage.gdrive_storage import GDriveStorage
from ..storage.komens_storage import KomensStorage
from ..storage.mail_storage import MailStorage

_LOGGER = logging.getLogger("bakalari.student_manager")


@dataclass
class StudentContext:
    """Holds all state for a single student."""

    name: str
    client: BakalariClient
    timetable_module: TimetableModule
    marks_module: MarksModule
    komens_module: KomensModule
    summary_module: SummaryModule
    prepare_module: PrepareModule
    komens_storage: KomensStorage
    gdrive_storage: GDriveStorage
    mail_storage: MailStorage
    gdrive_client: GoogleDriveClient | None = None
    mail_folder_id: str = ""
    student_info: str = ""

    # Cached data
    timetable: WeekTimetable | None = None
    marks: MarksData | None = None
    komens: MessagesData | None = None
    summary_current: SummaryData | None = None
    summary_last: SummaryData | None = None
    summary_next: SummaryData | None = None
    prepare_today: PrepareData | None = None
    prepare_tomorrow: PrepareData | None = None

    # Timestamps
    timetable_updated: datetime | None = None
    marks_updated: datetime | None = None
    komens_updated: datetime | None = None
    summary_updated: datetime | None = None
    prepare_updated: datetime | None = None


class StudentManager:
    """Manages API clients and cached data for all configured students."""

    def __init__(self) -> None:
        self._students: dict[str, StudentContext] = {}
        self._session: aiohttp.ClientSession | None = None
        self._gemini: GeminiClient | None = None
        self._config: AppConfig | None = None
        self._canteen_module: CanteenModule | None = None
        self._canteen: CanteenData | None = None
        self._canteen_updated: datetime | None = None

    @property
    def students(self) -> dict[str, StudentContext]:
        return self._students

    @property
    def gemini(self) -> GeminiClient | None:
        return self._gemini

    @property
    def canteen_module(self) -> CanteenModule | None:
        return self._canteen_module

    @property
    def canteen(self) -> CanteenData | None:
        return self._canteen

    @canteen.setter
    def canteen(self, value: CanteenData | None) -> None:
        self._canteen = value

    @property
    def canteen_updated(self) -> datetime | None:
        return self._canteen_updated

    @canteen_updated.setter
    def canteen_updated(self, value: datetime | None) -> None:
        self._canteen_updated = value

    @property
    def gdrive_available(self) -> bool:
        return any(ctx.gdrive_client is not None for ctx in self._students.values())

    @property
    def config(self) -> AppConfig | None:
        return self._config

    async def initialize(self, config: AppConfig) -> None:
        """Initialize all student clients and modules."""
        self._config = config
        self._session = aiohttp.ClientSession()

        # Initialize Gemini client
        if config.gemini_api_key:
            self._gemini = GeminiClient(config.gemini_api_key, session=self._session)
            _LOGGER.info("Gemini client initialized")

        # Initialize canteen module (school-wide, not per-student)
        canteen_cfg = config.canteen
        if canteen_cfg.cislo and canteen_cfg.s5url:
            self._canteen_module = CanteenModule(
                session=self._session,
                cislo=canteen_cfg.cislo,
                s5url=canteen_cfg.s5url,
                lang=canteen_cfg.lang,
            )
            _LOGGER.info("Canteen module initialized (cislo: %s)", canteen_cfg.cislo)

        app_data = get_app_data_dir()
        komens_base = app_data / "komens"
        gdrive_base = app_data / "gdrive"
        mail_base = app_data / "mail"

        for student_cfg in config.students:
            await self._setup_student(student_cfg, config, komens_base, gdrive_base, mail_base)

    async def _setup_student(
        self,
        cfg: StudentConfig,
        app_config: AppConfig,
        komens_base: Path,
        gdrive_base: Path,
        mail_base: Path,
    ) -> None:
        """Set up a single student context."""
        client = BakalariClient(app_config.base_url, cfg.username, cfg.password, session=self._session)

        try:
            await client.login()
            _LOGGER.info("Logged in student: %s", cfg.name)
        except Exception as err:
            _LOGGER.error("Failed to login student %s: %s", cfg.name, err)
            raise

        komens_storage = KomensStorage(komens_base, cfg.name)
        komens_storage.load_index()

        gdrive_storage = GDriveStorage(gdrive_base, cfg.name)

        mail_storage = MailStorage(mail_base, cfg.name)
        mail_storage.load_index()

        # Create per-student Google Drive client
        gdrive_client = None
        gdrive_cfg = app_config.gdrive
        folder_id = cfg.gdrive_folder_id or gdrive_cfg.reports_folder_id
        if gdrive_cfg.service_account_path and folder_id:
            school_start = None
            if gdrive_cfg.school_year_start:
                try:
                    school_start = date.fromisoformat(gdrive_cfg.school_year_start)
                except ValueError:
                    pass
            gdrive_client = GoogleDriveClient(
                service_account_path=gdrive_cfg.service_account_path,
                reports_folder_id=folder_id,
                session=self._session,
                school_year_start=school_start,
            )
            _LOGGER.info("Google Drive client initialized for %s (folder: %s)", cfg.name, folder_id)

        komens_path = komens_storage.storage_path

        ctx = StudentContext(
            name=cfg.name,
            client=client,
            timetable_module=TimetableModule(client),
            marks_module=MarksModule(client),
            komens_module=KomensModule(client),
            summary_module=SummaryModule(komens_path, cfg.name),
            prepare_module=PrepareModule(komens_path, cfg.name),
            komens_storage=komens_storage,
            gdrive_storage=gdrive_storage,
            mail_storage=mail_storage,
            gdrive_client=gdrive_client,
            mail_folder_id=cfg.mail_folder_id,
            student_info=cfg.student_info,
        )
        self._students[cfg.name] = ctx

    def get_student(self, name: str) -> StudentContext | None:
        return self._students.get(name)

    def student_names(self) -> list[str]:
        return list(self._students.keys())

    async def shutdown(self) -> None:
        """Close all clients and session."""
        for ctx in self._students.values():
            try:
                await ctx.client.close()
            except Exception:
                pass

        if self._gemini:
            await self._gemini.close()

        if self._session and not self._session.closed:
            await self._session.close()

        self._students.clear()
        _LOGGER.info("Student manager shut down")
