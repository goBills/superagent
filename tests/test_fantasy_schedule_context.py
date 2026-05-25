"""
Tests for Phase 7C-lite: fantasy schedule context tools.
"""

import json
import sys
from pathlib import Path

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from superagent.tool_schemas import TOOL_DISPATCH, TOOL_SCHEMAS
from superagent.tools import compare_fantasy_context, get_fantasy_schedule_context


MISSING_KEYS = {"injuries", "depth_chart", "projections"}


class TestFantasyScheduleContext:
    """Test get_fantasy_schedule_context."""

    def test_get_fantasy_schedule_context_josh_allen_2025(self):
        result = get_fantasy_schedule_context("Josh Allen", 2025)

        assert result["ok"] == True
        data = result["data"]
        assert data["player_name"] == "Josh Allen"
        assert data["position"] == "QB"
        assert data["team"] == "BUF"
        assert data["season"] == 2025
        assert isinstance(data["team_bye_week"], int)
        assert data["games_from_week"]
        assert data["weekly_usage"]
        assert "usage_trend" in data
        assert set(data["missing_context"]) == MISSING_KEYS
        assert result["meta"]["from_week"] == 1
        assert result["meta"]["usage_source"] == "pbp_derived"
        assert "2025_note" in result["meta"]

    def test_get_fantasy_schedule_context_from_week_filtering(self):
        result = get_fantasy_schedule_context("James Cook", 2024, from_week=10)

        assert result["ok"] == True
        data = result["data"]
        assert data["games_from_week"]
        assert all(game["week"] >= 10 for game in data["games_from_week"])
        assert min(week["week"] for week in data["weekly_usage"]) == 1
        assert data["usage_trend"]["early_period"]["weeks"] == "1-8"
        assert data["usage_trend"]["late_period"]["weeks"] == "9-17"
        assert result["meta"]["from_week"] == 10

    def test_get_fantasy_schedule_context_rb_james_cook(self):
        result = get_fantasy_schedule_context("James Cook", 2024)

        assert result["ok"] == True
        data = result["data"]
        assert data["position"] == "RB"
        assert data["team_bye_week"] == 12
        assert data["weekly_usage"]
        first_week = data["weekly_usage"][0]
        assert "carries" in first_week
        assert "targets" in first_week
        assert "rushing_yards" in first_week
        assert "receiving_yards" in first_week
        assert "fantasy_points_ppr" in first_week
        assert data["usage_trend"]["change"]["status"] in {"trending_up", "trending_down", "stable"}

    def test_get_fantasy_schedule_context_invalid_player(self):
        result = get_fantasy_schedule_context("Not A Real Player", 2024)

        assert result["ok"] == False
        assert result["error"]

    def test_get_fantasy_schedule_context_invalid_from_week(self):
        result = get_fantasy_schedule_context("Josh Allen", 2024, from_week=0)

        assert result["ok"] == False
        assert "from_week" in result["error"]

    def test_missing_context_always_present(self):
        result = get_fantasy_schedule_context("Khalil Shakir", 2024)

        assert result["ok"] == True
        missing_context = result["data"]["missing_context"]
        assert set(missing_context) == MISSING_KEYS
        assert "injury" in missing_context["injuries"].lower()
        assert "depth" in missing_context["depth_chart"].lower()
        assert "projection" in missing_context["projections"].lower()

    def test_get_fantasy_schedule_context_json_serializable(self):
        result = get_fantasy_schedule_context("Josh Allen", 2025)

        assert result["ok"] == True
        json.dumps(result)


class TestCompareFantasyContext:
    """Test compare_fantasy_context."""

    def test_compare_fantasy_context_two_bills_players(self):
        result = compare_fantasy_context(["James Cook", "Khalil Shakir"], 2024)

        assert result["ok"] == True
        assert len(result["data"]) == 2
        assert result["meta"]["players_compared"] == 2
        names = {row["player_name"] for row in result["data"]}
        assert names == {"James Cook", "Khalil Shakir"}
        for row in result["data"]:
            assert row["team"] == "BUF"
            assert row["team_bye_week"] == 12
            assert row["games_from_week"]
            assert "usage_trend" in row
            assert set(row["missing_context"]) == MISSING_KEYS
            assert "weekly_usage" not in row

    def test_compare_fantasy_context_from_week(self):
        result = compare_fantasy_context(["James Cook", "Khalil Shakir"], 2024, from_week=10)

        assert result["ok"] == True
        assert result["meta"]["from_week"] == 10
        for row in result["data"]:
            assert row["games_from_week"]
            assert all(game["week"] >= 10 for game in row["games_from_week"])

    def test_compare_fantasy_context_with_invalid_player_preserves_error_row(self):
        result = compare_fantasy_context(["James Cook", "Not A Real Player"], 2024)

        assert result["ok"] == True
        assert len(result["data"]) == 2
        assert result["meta"]["players_compared"] == 1
        assert any(row.get("error") for row in result["data"])

    def test_compare_fantasy_context_empty_list(self):
        result = compare_fantasy_context([], 2024)

        assert result["ok"] == False
        assert "cannot be empty" in result["error"]

    def test_compare_fantasy_context_all_invalid(self):
        result = compare_fantasy_context(["Not A Real Player"], 2024)

        assert result["ok"] == False
        assert "Could not build fantasy context" in result["error"]

    def test_compare_fantasy_context_json_serializable(self):
        result = compare_fantasy_context(["James Cook", "Khalil Shakir"], 2024, from_week=10)

        assert result["ok"] == True
        json.dumps(result)


class TestFantasyScheduleContextSchemas:
    """Test Claude schema integration for Phase 7C-lite tools."""

    @pytest.mark.parametrize(
        "tool_name",
        ["get_fantasy_schedule_context", "compare_fantasy_context"],
    )
    def test_context_tools_are_in_dispatch(self, tool_name):
        assert tool_name in TOOL_DISPATCH
        assert callable(TOOL_DISPATCH[tool_name])

    @pytest.mark.parametrize(
        "tool_name",
        ["get_fantasy_schedule_context", "compare_fantasy_context"],
    )
    def test_context_tools_have_schemas(self, tool_name):
        schema_names = {schema["name"] for schema in TOOL_SCHEMAS}
        assert tool_name in schema_names
