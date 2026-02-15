"""Canteen module for Strava.cz school meal API."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import aiohttp

from ..const import CANTEEN_API_URL

_LOGGER = logging.getLogger("bakalari.canteen")


@dataclass
class CanteenMeal:
    """A single meal item in the canteen menu."""

    druh: str  # PR, PO, OB, DO, SV, OD
    druh_popis: str  # e.g. "Přesnídávka", "Polévka", "Oběd"
    nazev: str
    alergeny: list[tuple[str, str]] = field(default_factory=list)

    @classmethod
    def from_api_response(cls, item: dict[str, Any]) -> CanteenMeal:
        """Parse a meal from the Strava API response."""
        alergeny = []
        for pair in item.get("alergeny", []):
            if isinstance(pair, list) and len(pair) == 2:
                alergeny.append((pair[0], pair[1]))
        return cls(
            druh=item.get("druh", ""),
            druh_popis=item.get("druh_popis", "").strip(),
            nazev=item.get("nazev", "").strip(),
            alergeny=alergeny,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "druh": self.druh,
            "druh_popis": self.druh_popis,
            "nazev": self.nazev,
            "alergeny": [{"code": a[0], "name": a[1]} for a in self.alergeny],
        }


@dataclass
class CanteenDay:
    """All meals for a single day."""

    date: date
    meals: list[CanteenMeal] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date.isoformat(),
            "date_label": self.date.strftime("%d.%m.%Y"),
            "day_name": _CZECH_DAYS[self.date.weekday()],
            "meals": [m.to_dict() for m in self.meals],
        }


@dataclass
class CanteenData:
    """Complete canteen menu data."""

    days: list[CanteenDay] = field(default_factory=list)
    fetched_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "days": [d.to_dict() for d in self.days],
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
        }


_CZECH_DAYS = ["Pondělí", "Úterý", "Středa", "Čtvrtek", "Pátek", "Sobota", "Neděle"]


def _parse_date(date_str: str) -> date | None:
    """Parse date from 'DD.MM.YYYY' format."""
    try:
        return datetime.strptime(date_str, "%d.%m.%Y").date()
    except (ValueError, TypeError):
        return None


def parse_canteen_response(data: list[dict[str, Any]]) -> list[CanteenDay]:
    """Parse the Strava API response into CanteenDay objects."""
    days_by_date: dict[date, list[CanteenMeal]] = {}

    if not data:
        return []

    entry = data[0] if data else {}

    for key in sorted(entry.keys()):
        if not key.startswith("table"):
            continue
        items = entry[key]
        if not isinstance(items, list):
            continue

        for item in items:
            datum_str = item.get("datum", "")
            parsed_date = _parse_date(datum_str)
            if parsed_date is None:
                continue

            nazev = item.get("nazev", "").strip()
            if not nazev:
                continue

            meal = CanteenMeal.from_api_response(item)
            days_by_date.setdefault(parsed_date, []).append(meal)

    days = []
    for d in sorted(days_by_date.keys()):
        days.append(CanteenDay(date=d, meals=days_by_date[d]))

    return days


class CanteenModule:
    """Fetches canteen menu from Strava.cz API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        cislo: str,
        s5url: str,
        lang: str = "CZ",
    ) -> None:
        self._session = session
        self._cislo = cislo
        self._s5url = s5url
        self._lang = lang

    async def get_menu(self) -> CanteenData:
        """Fetch the current canteen menu."""
        payload = {
            "cislo": self._cislo,
            "s5url": self._s5url,
            "lang": self._lang,
            "ignoreCert": False,
        }

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
            "Content-Type": "text/plain;charset=UTF-8",
            "Origin": "https://app.strava.cz",
            "Referer": f"https://app.strava.cz/jidelnicky?jidelna={self._cislo}",
        }

        async with self._session.post(CANTEEN_API_URL, data=json.dumps(payload), headers=headers) as resp:
            raw = await resp.json(content_type=None)
            if isinstance(raw, dict) and raw.get("state") == "error":
                msg = raw.get("message", "Unknown error")
                raise RuntimeError(f"Strava API error: {msg}")
            resp.raise_for_status()

        days = parse_canteen_response(raw)
        _LOGGER.debug("Fetched canteen menu: %d days", len(days))

        return CanteenData(days=days, fetched_at=datetime.now())
