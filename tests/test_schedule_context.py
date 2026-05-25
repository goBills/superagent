"""
Tests for Phase 7A: schedule and bye week context tools.
"""

import json
import sys
from pathlib import Path

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from superagent.tool_schemas import TOOL_DISPATCH, TOOL_SCHEMAS
from superagent.tools import get_bye_weeks, get_team_schedule_context, get_upcoming_games


class TestTeamScheduleContext:
    """Test get_team_schedule_context."""

    def test_bills_2024_schedule_includes_bye(self):
        result = get_team_schedule_context("Bills", 2024)

        assert result["ok"] == True
        data = result["data"]
        assert data["team"] == "BUF"
        assert data["season"] == 2024
        assert data["bye_week"] == 12
        assert len(data["schedule"]) == 18

        bye_rows = [row for row in data["schedule"] if row.get("bye")]
        assert len(bye_rows) == 1
        assert bye_rows[0]["week"] == 12
        assert bye_rows[0]["opponent"] is None

    def test_bills_2024_schedule_game_shape(self):
        result = get_team_schedule_context("BUF", 2024)

        assert result["ok"] == True
        games = [row for row in result["data"]["schedule"] if not row.get("bye")]
        assert games
        first = games[0]
        assert first["week"] == 1
        assert first["game_id"]
        assert first["opponent"] == "ARI"
        assert first["location"] == "home"
        assert first["game_date"] == "2024-09-08"
        assert first["result"] in ("W", "L", "T", None)
        assert isinstance(first["team_score"], int)
        assert isinstance(first["opponent_score"], int)

    def test_schedule_invalid_team(self):
        result = get_team_schedule_context("NotATeam", 2024)

        assert result["ok"] == False
        assert "Could not resolve team" in result["error"]

    def test_schedule_json_serializable(self):
        result = get_team_schedule_context("Bills", 2024)

        assert result["ok"] == True
        json.dumps(result)


class TestByeWeeks:
    """Test get_bye_weeks."""

    def test_bills_bye_week_2024(self):
        result = get_bye_weeks(2024, "Bills")

        assert result["ok"] == True
        assert result["data"] == {"season": 2024, "team": "BUF", "bye_week": 12}

    def test_all_bye_weeks_2024(self):
        result = get_bye_weeks(2024)

        assert result["ok"] == True
        bye_weeks = result["data"]["bye_weeks"]
        assert "12" in bye_weeks
        assert "BUF" in bye_weeks["12"]
        assert result["meta"]["teams_count"] == 32

        teams = [team for teams in bye_weeks.values() for team in teams]
        assert len(teams) == 32
        assert len(set(teams)) == 32

    def test_all_bye_weeks_are_sorted_for_stability(self):
        result = get_bye_weeks(2024)

        assert result["ok"] == True
        bye_weeks = result["data"]["bye_weeks"]
        assert list(bye_weeks.keys()) == sorted(bye_weeks.keys(), key=int)
        for teams in bye_weeks.values():
            assert teams == sorted(teams)

    def test_bye_weeks_invalid_team(self):
        result = get_bye_weeks(2024, "NotATeam")

        assert result["ok"] == False
        assert "Could not resolve team" in result["error"]


class TestUpcomingGames:
    """Test get_upcoming_games."""

    def test_upcoming_games_from_week_10(self):
        result = get_upcoming_games("Bills", 2024, 10)

        assert result["ok"] == True
        data = result["data"]
        assert data["team"] == "BUF"
        assert data["from_week"] == 10
        assert len(data["games"]) == 8
        assert all(game["week"] >= 10 for game in data["games"])

        first = data["games"][0]
        assert first["game_id"]
        assert first["opponent"] == "IND"
        assert first["location"] == "away"
        assert first["team_score"] == 30
        assert first["opponent_score"] == 20

    def test_upcoming_games_default_from_week(self):
        result = get_upcoming_games("BUF", 2024)

        assert result["ok"] == True
        assert result["data"]["from_week"] == 1
        assert result["meta"]["from_week_default"] == "1 when not provided"

    def test_upcoming_games_invalid_from_week(self):
        result = get_upcoming_games("BUF", 2024, 0)

        assert result["ok"] == False
        assert "from_week" in result["error"]

    def test_upcoming_games_invalid_team(self):
        result = get_upcoming_games("NotATeam", 2024, 10)

        assert result["ok"] == False
        assert "Could not resolve team" in result["error"]

    def test_upcoming_games_json_serializable(self):
        result = get_upcoming_games("Bills", 2024, 10)

        assert result["ok"] == True
        json.dumps(result)


class TestScheduleToolSchemas:
    """Test Claude schema integration for Phase 7A tools."""

    @pytest.mark.parametrize(
        "tool_name",
        ["get_team_schedule_context", "get_bye_weeks", "get_upcoming_games"],
    )
    def test_schedule_tools_are_in_dispatch(self, tool_name):
        assert tool_name in TOOL_DISPATCH
        assert callable(TOOL_DISPATCH[tool_name])

    @pytest.mark.parametrize(
        "tool_name",
        ["get_team_schedule_context", "get_bye_weeks", "get_upcoming_games"],
    )
    def test_schedule_tools_have_schemas(self, tool_name):
        schema_names = {schema["name"] for schema in TOOL_SCHEMAS}
        assert tool_name in schema_names
