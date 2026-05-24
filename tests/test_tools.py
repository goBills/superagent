"""
Pytest tests for Superagent tools.

Sanity checks against known 2024 Bills data.
Real NFL stats, not mocks.
"""

import sys
from pathlib import Path

# Add src to path so we can import superagent
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from superagent.name_resolution import resolve_team, resolve_player, search_players
from superagent.tools import (
    get_team_summary,
    get_player_summary,
    compare_players,
    get_team_epa_trend
)


class TestNameResolution:
    """Test name resolution functions."""

    def test_resolve_team_bills(self):
        """Test resolving Buffalo Bills team name."""
        result = resolve_team("Bills")
        assert result["ok"] == True
        assert result["team"] == "BUF"

    def test_resolve_team_bills_full_name(self):
        """Test resolving full Buffalo name."""
        result = resolve_team("Buffalo")
        assert result["ok"] == True
        assert result["team"] == "BUF"

    def test_resolve_team_bills_lowercase(self):
        """Test resolving team name case-insensitive."""
        result = resolve_team("buffalo")
        assert result["ok"] == True
        assert result["team"] == "BUF"

    def test_resolve_team_invalid(self):
        """Test resolving invalid team name."""
        result = resolve_team("NotATeam")
        assert result["ok"] == False
        assert result["error"] is not None

    def test_resolve_team_empty(self):
        """Test resolving empty team name."""
        result = resolve_team("")
        assert result["ok"] == False

    def test_resolve_player_josh_allen_2024(self):
        """Test resolving Josh Allen for 2024."""
        result = resolve_player("Josh Allen", 2024)
        assert result["ok"] == True
        assert result["player_id"] is not None
        assert result["name"] is not None
        assert result["position"] == "QB"
        assert result["team"] == "BUF"

    def test_resolve_player_invalid_2024(self):
        """Test resolving invalid player name."""
        result = resolve_player("NotARealPlayer", 2024)
        assert result["ok"] == False

    def test_resolve_player_empty(self):
        """Test resolving empty player name."""
        result = resolve_player("", 2024)
        assert result["ok"] == False

    def test_resolve_player_invalid_season(self):
        """Test resolving player with invalid season."""
        result = resolve_player("Josh Allen", 2019)  # Before 2020
        assert result["ok"] == False

    def test_search_players_partial_name(self):
        """Test searching for players by partial name."""
        result = search_players("Josh", 2024, limit=5)
        assert result["ok"] == True
        assert isinstance(result["candidates"], list)
        assert len(result["candidates"]) > 0
        # At least one Josh should be in results
        josh_found = any("josh" in str(c["name"]).lower() for c in result["candidates"])
        assert josh_found


class TestToolsBasic:
    """Test basic tool functionality."""

    def test_get_team_summary_2024_bills(self):
        """Test getting 2024 Buffalo Bills team summary."""
        result = get_team_summary("BUF", 2024)
        assert result["ok"] == True
        assert result["data"] is not None

        data = result["data"]
        assert data["team"] == "BUF"
        assert data["season"] == 2024
        # 2024 NFL regular season is 17 games, but we may have include post-season
        assert data["games"] >= 17
        assert data["wins"] > 0
        assert data["losses"] >= 0
        assert data["wins"] + data["losses"] >= 17
        assert data["points_for"] > 0
        assert data["points_against"] > 0
        assert data["offensive_epa"] is not None
        assert data["offensive_epa_per_play"] is not None

    def test_get_team_summary_invalid_team(self):
        """Test team summary with invalid team."""
        result = get_team_summary("NotATeam", 2024)
        assert result["ok"] == False
        assert result["error"] is not None

    def test_get_player_summary_josh_allen_2024(self):
        """Test getting Josh Allen 2024 player summary."""
        result = get_player_summary("Josh Allen", 2024)
        assert result["ok"] == True
        assert result["data"] is not None

        data = result["data"]
        assert data["player_id"] is not None
        assert data["name"] is not None
        assert data["position"] == "QB"
        assert data["team"] == "BUF"
        assert data["games"] > 0
        assert data["passing_yards"] > 0
        assert data["passing_tds"] >= 0
        assert data["interceptions"] >= 0
        # QB should have completion pct
        assert data.get("completion_pct", 0) > 0

    def test_get_player_summary_invalid_player(self):
        """Test player summary with invalid player."""
        result = get_player_summary("NotARealPlayer", 2024)
        assert result["ok"] == False
        assert result["error"] is not None

    def test_compare_players_2024(self):
        """Test comparing multiple players."""
        result = compare_players(
            ["Josh Allen", "Lamar Jackson"],
            2024,
            ["passing_yards", "passing_tds", "completion_pct"]
        )
        assert result["ok"] == True
        assert result["data"] is not None
        assert len(result["data"]) == 2

        # Both should be QBs with passing stats
        for player in result["data"]:
            if "error" not in player:
                assert player["position"] == "QB"
                assert "passing_yards" in player
                assert "passing_tds" in player

    def test_compare_players_empty_list(self):
        """Test comparing with empty player list."""
        result = compare_players([], 2024)
        assert result["ok"] == False

    def test_get_team_epa_trend_2024_bills(self):
        """Test getting 2024 Buffalo Bills EPA trend."""
        result = get_team_epa_trend("BUF", 2024, 1, 17)
        assert result["ok"] == True
        assert result["data"] is not None

        data = result["data"]
        assert len(data) > 0
        # Should have data for weeks in range
        weeks = [d["week"] for d in data]
        assert min(weeks) >= 1
        assert max(weeks) <= 17

        # Check EPA data structure
        for week_data in data:
            assert "week" in week_data
            assert "offensive_epa" in week_data
            assert "defensive_epa_allowed" in week_data or "defensive_epa" in week_data
            assert "net_epa" in week_data
            assert isinstance(week_data["week"], int)
            assert isinstance(week_data["offensive_epa"], (int, float))

    def test_get_team_epa_trend_partial_weeks(self):
        """Test EPA trend for partial season."""
        result = get_team_epa_trend("BUF", 2024, 6, 10)
        assert result["ok"] == True
        assert result["data"] is not None

        weeks = [d["week"] for d in result["data"]]
        assert len(weeks) <= 5  # Weeks 6-10 inclusive

    def test_output_formats_json_serializable(self):
        """Test that all outputs are JSON-serializable."""
        import json

        # Test team summary
        result = get_team_summary("BUF", 2024)
        assert result["ok"] == True
        json.dumps(result)  # Should not raise

        # Test player summary
        result = get_player_summary("Josh Allen", 2024)
        assert result["ok"] == True
        json.dumps(result)  # Should not raise

        # Test compare players
        result = compare_players(["Josh Allen"], 2024)
        assert result["ok"] == True
        json.dumps(result)  # Should not raise

        # Test EPA trend
        result = get_team_epa_trend("BUF", 2024, 1, 5)
        assert result["ok"] == True
        json.dumps(result)  # Should not raise


class TestToolsMetadata:
    """Test tool output metadata and error handling."""

    def test_team_summary_meta(self):
        """Test team summary metadata."""
        result = get_team_summary("BUF", 2024)
        assert result["ok"] == True
        assert "meta" in result
        assert result["meta"]["team_abbr"] == "BUF"
        assert result["meta"]["source"] is not None

    def test_player_summary_meta(self):
        """Test player summary metadata."""
        result = get_player_summary("Josh Allen", 2024)
        assert result["ok"] == True
        assert "meta" in result
        assert result["meta"]["player_id"] is not None
        assert result["meta"]["source"] is not None

    def test_2025_player_stats_are_pbp_derived(self):
        """Test that 2025 player stats are marked as pbp_derived."""
        result = get_player_summary("Josh Allen", 2025)
        # May fail if no 2025 data, but if it succeeds, check source
        if result["ok"] and result["data"]:
            assert result["meta"]["source"] == "pbp_derived"


class TestToolsErrorHandling:
    """Test error handling and edge cases."""

    def test_team_summary_wrong_season(self):
        """Test team summary with future season."""
        result = get_team_summary("BUF", 2026)
        # Should either fail or return empty
        if result["ok"]:
            assert result["data"] is None or result["data"]["games"] == 0

    def test_player_summary_wrong_season(self):
        """Test player summary with wrong season."""
        result = get_player_summary("Josh Allen", 2019)
        assert result["ok"] == False

    def test_compare_players_mixed_validity(self):
        """Test comparing with mix of valid and invalid players."""
        result = compare_players(
            ["Josh Allen", "NotARealPlayer"],
            2024
        )
        # Should still return data, but with error for one
        assert result["ok"] == True
        assert len(result["data"]) == 2
        errors_found = sum(1 for p in result["data"] if "error" in p)
        assert errors_found >= 1  # At least one should error


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
