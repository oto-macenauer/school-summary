"""Tests for the canteen module."""

from __future__ import annotations

import json
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.canteen import (
    CanteenData,
    CanteenDay,
    CanteenMeal,
    CanteenModule,
    parse_canteen_response,
)

from .conftest import load_fixture


@pytest.fixture
def canteen_response() -> list[dict[str, Any]]:
    """Load canteen fixture."""
    return load_fixture("canteen_response.json")


class TestCanteenMeal:
    """Tests for CanteenMeal dataclass."""

    def test_from_api_response(self) -> None:
        """Test creating a meal from API response."""
        item = {
            "druh": "OB",
            "druh_popis": "Oběd ",
            "nazev": "Krůtí na smetaně, rýže",
            "alergeny": [["01", "Obiloviny"], ["07", "Mléko"]],
        }
        meal = CanteenMeal.from_api_response(item)

        assert meal.druh == "OB"
        assert meal.druh_popis == "Oběd"
        assert meal.nazev == "Krůtí na smetaně, rýže"
        assert len(meal.alergeny) == 2
        assert meal.alergeny[0] == ("01", "Obiloviny")

    def test_from_api_response_no_allergens(self) -> None:
        """Test meal with no allergens."""
        item = {
            "druh": "DO",
            "druh_popis": "Doplněk ",
            "nazev": "Čaj, mošt",
            "alergeny": [],
        }
        meal = CanteenMeal.from_api_response(item)

        assert meal.alergeny == []
        assert meal.nazev == "Čaj, mošt"

    def test_from_api_response_missing_fields(self) -> None:
        """Test meal with missing fields."""
        meal = CanteenMeal.from_api_response({})

        assert meal.druh == ""
        assert meal.druh_popis == ""
        assert meal.nazev == ""
        assert meal.alergeny == []

    def test_to_dict(self) -> None:
        """Test meal serialization."""
        meal = CanteenMeal(
            druh="PO",
            druh_popis="Polévka",
            nazev="Gulášová",
            alergeny=[("01", "Obiloviny")],
        )
        d = meal.to_dict()

        assert d["druh"] == "PO"
        assert d["druh_popis"] == "Polévka"
        assert d["nazev"] == "Gulášová"
        assert d["alergeny"] == [{"code": "01", "name": "Obiloviny"}]


class TestCanteenDay:
    """Tests for CanteenDay dataclass."""

    def test_to_dict(self) -> None:
        """Test day serialization."""
        day = CanteenDay(
            date=date(2026, 2, 11),
            meals=[
                CanteenMeal(druh="OB", druh_popis="Oběd", nazev="Řízek", alergeny=[]),
            ],
        )
        d = day.to_dict()

        assert d["date"] == "2026-02-11"
        assert d["date_label"] == "11.02.2026"
        assert d["day_name"] == "Středa"
        assert len(d["meals"]) == 1

    def test_day_name_monday(self) -> None:
        """Test Czech day name for Monday."""
        day = CanteenDay(date=date(2026, 2, 9), meals=[])
        assert day.to_dict()["day_name"] == "Pondělí"

    def test_day_name_friday(self) -> None:
        """Test Czech day name for Friday."""
        day = CanteenDay(date=date(2026, 2, 13), meals=[])
        assert day.to_dict()["day_name"] == "Pátek"


class TestParseCanteenResponse:
    """Tests for response parsing."""

    def test_parse_full_response(self, canteen_response: list[dict[str, Any]]) -> None:
        """Test parsing a full API response."""
        days = parse_canteen_response(canteen_response)

        assert len(days) == 2
        assert days[0].date == date(2026, 2, 11)
        assert days[1].date == date(2026, 2, 12)

    def test_parse_meals_count(self, canteen_response: list[dict[str, Any]]) -> None:
        """Test meal count per day."""
        days = parse_canteen_response(canteen_response)

        # Day 1: 5 meals (PR, PO, OB, OD, DO) - OD has "Oběd dieta" which is non-empty
        assert len(days[0].meals) == 5
        # Day 2: 3 meals (PR, PO, OB)
        assert len(days[1].meals) == 3

    def test_parse_first_meal(self, canteen_response: list[dict[str, Any]]) -> None:
        """Test parsing of the first meal."""
        days = parse_canteen_response(canteen_response)
        first_meal = days[0].meals[0]

        assert first_meal.druh == "PR"
        assert first_meal.druh_popis == "Přesnídávka"
        assert first_meal.nazev == "Pomazánka z pečené dýně, veka"
        assert len(first_meal.alergeny) == 2

    def test_parse_allergens(self, canteen_response: list[dict[str, Any]]) -> None:
        """Test allergen parsing."""
        days = parse_canteen_response(canteen_response)
        soup = days[0].meals[1]  # Polévka

        assert soup.druh == "PO"
        assert len(soup.alergeny) == 4
        assert soup.alergeny[0] == ("01", "Obiloviny obsahující lepek")
        assert soup.alergeny[3] == ("09", "Celer")

    def test_parse_sorted_by_date(self, canteen_response: list[dict[str, Any]]) -> None:
        """Test that days are sorted chronologically."""
        days = parse_canteen_response(canteen_response)

        dates = [d.date for d in days]
        assert dates == sorted(dates)

    def test_parse_empty_response(self) -> None:
        """Test parsing empty response."""
        assert parse_canteen_response([]) == []

    def test_parse_empty_tables(self) -> None:
        """Test parsing response with no table keys."""
        assert parse_canteen_response([{}]) == []

    def test_parse_invalid_date(self) -> None:
        """Test parsing with invalid date skips the item."""
        data = [{"table0": [{"datum": "invalid", "nazev": "Test", "druh": "OB", "druh_popis": "Oběd", "alergeny": []}]}]
        days = parse_canteen_response(data)
        assert len(days) == 0

    def test_parse_empty_nazev_skipped(self) -> None:
        """Test that items with empty nazev are skipped."""
        data = [{"table0": [{"datum": "11.02.2026", "nazev": "", "druh": "OB", "druh_popis": "Oběd", "alergeny": []}]}]
        days = parse_canteen_response(data)
        assert len(days) == 0


class TestCanteenData:
    """Tests for CanteenData dataclass."""

    def test_to_dict(self) -> None:
        """Test CanteenData serialization."""
        data = CanteenData(
            days=[CanteenDay(date=date(2026, 2, 11), meals=[])],
        )
        d = data.to_dict()

        assert len(d["days"]) == 1
        assert d["fetched_at"] is None

    def test_to_dict_empty(self) -> None:
        """Test empty CanteenData serialization."""
        data = CanteenData()
        d = data.to_dict()

        assert d["days"] == []
        assert d["fetched_at"] is None


class TestCanteenModule:
    """Tests for CanteenModule."""

    @pytest.mark.asyncio
    async def test_get_menu(self, canteen_response: list[dict[str, Any]]) -> None:
        """Test fetching canteen menu."""
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = AsyncMock(return_value=canteen_response)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_resp)

        module = CanteenModule(
            session=mock_session,
            cislo="11199",
            s5url="https://wss52.strava.cz/WSStravne5_4/WSStravne5.svc",
        )
        result = await module.get_menu()

        assert isinstance(result, CanteenData)
        assert len(result.days) == 2
        assert result.fetched_at is not None

        mock_session.post.assert_called_once()
        call_args = mock_session.post.call_args
        sent_body = json.loads(call_args[1]["data"])
        assert sent_body["cislo"] == "11199"

    @pytest.mark.asyncio
    async def test_get_menu_strava_api_error(self) -> None:
        """Test handling Strava API error response (HTTP 555)."""
        error_body = {"state": "error", "number": "99+", "message": "Chyba odchycena v api callu"}
        mock_resp = AsyncMock()
        mock_resp.status = 555
        mock_resp.json = AsyncMock(return_value=error_body)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_resp)

        module = CanteenModule(
            session=mock_session,
            cislo="11199",
            s5url="https://example.com",
        )

        with pytest.raises(RuntimeError, match="Strava API error: Chyba odchycena v api callu"):
            await module.get_menu()

    @pytest.mark.asyncio
    async def test_get_menu_http_error(self) -> None:
        """Test handling non-Strava HTTP error."""
        mock_resp = AsyncMock()
        mock_resp.status = 500
        mock_resp.json = AsyncMock(return_value={})
        mock_resp.raise_for_status = MagicMock(side_effect=Exception("Server error"))
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_resp)

        module = CanteenModule(
            session=mock_session,
            cislo="11199",
            s5url="https://example.com",
        )

        with pytest.raises(Exception, match="Server error"):
            await module.get_menu()
