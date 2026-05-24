"""
Tests for Phase 4A: Fantasy research tools.

Tests deterministic fantasy scoring and player summary functions.
"""

import sys
from pathlib import Path

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from superagent.tools import (
    get_fantasy_player_summary,
    compare_fantasy_players,
    get_player_weekly_usage,
    _calculate_fantasy_points,
)


class TestFantasyScoring:
    """Test fantasy point calculations."""

    def test_fantasy_scoring_ppr(self):
        """Test PPR scoring calculation."""
        # QB example: 300 pass yards, 2 TDs, 1 INT, 10 receptions
        # Standard: 300*0.04 + 2*4 - 1*2 = 12 + 8 - 2 = 18
        # PPR: 18 + 10*1 = 28
        points = _calculate_fantasy_points(
            pass_yds=300, pass_td=2, interceptions=1,
            rush_yds=0, rush_td=0,
            rec_yds=0, rec_td=0,
            receptions=10,
            scoring="ppr"
        )
        assert points == 28.0

    def test_fantasy_scoring_half_ppr(self):
        """Test half-PPR scoring calculation."""
        # Same example: 18 + 10*0.5 = 23
        points = _calculate_fantasy_points(
            pass_yds=300, pass_td=2, interceptions=1,
            rush_yds=0, rush_td=0,
            rec_yds=0, rec_td=0,
            receptions=10,
            scoring="half_ppr"
        )
        assert points == 23.0

    def test_fantasy_scoring_standard(self):
        """Test standard scoring calculation."""
        # Same example: 18 (no reception bonus)
        points = _calculate_fantasy_points(
            pass_yds=300, pass_td=2, interceptions=1,
            rush_yds=0, rush_td=0,
            rec_yds=0, rec_td=0,
            receptions=10,
            scoring="standard"
        )
        assert points == 18.0

    def test_fantasy_scoring_rb(self):
        """Test RB fantasy scoring."""
        # RB: 150 rush yards, 1 TD, 8 receptions, 60 receiving yards
        # Standard: 150*0.1 + 1*6 + 60*0.1 = 15 + 6 + 6 = 27
        # PPR: 27 + 8*1 = 35
        points = _calculate_fantasy_points(
            pass_yds=0, pass_td=0, interceptions=0,
            rush_yds=150, rush_td=1,
            rec_yds=60, rec_td=0,
            receptions=8,
            scoring="ppr"
        )
        assert points == 35.0


class TestFantasyPlayerSummary:
    """Test get_fantasy_player_summary function."""

    def test_get_fantasy_player_summary_josh_allen_2024(self):
        """Test Josh Allen 2024 fantasy summary."""
        result = get_fantasy_player_summary("Josh Allen", 2024, scoring="ppr")

        assert result["ok"] == True
        assert result["data"] is not None
        data = result["data"]

        # Validate structure
        assert data["name"] == "Josh Allen"
        assert data["position"] == "QB"
        assert data["team"] == "BUF"
        assert data["season"] == 2024
        assert data["games"] >= 16  # At least 16 regular season games
        assert data["scoring"] == "ppr"

        # Josh Allen 2024: ~4367 passing yards, ~32 TDs, ~6 INTs (approximate)
        # These may vary slightly depending on data source
        assert data["passing_yards"] > 4000
        assert data["passing_tds"] >= 30
        assert data["interceptions"] >= 5
        assert data["rushing_yards"] > 400
        assert data["rushing_tds"] >= 2

        # Fantasy points should be calculated
        assert data["fantasy_points"] > 0
        assert data["fantasy_points_per_game"] > 0

        # Check meta
        assert result["meta"]["source"] in ("weekly", "pbp_derived")
        assert result["meta"]["scoring_format"] == "ppr"

    def test_get_fantasy_player_summary_lamar_jackson_2024(self):
        """Test Lamar Jackson 2024 fantasy summary."""
        result = get_fantasy_player_summary("Lamar Jackson", 2024, scoring="ppr")

        # Lamar Jackson may not be in the database with that exact name
        if not result["ok"]:
            pytest.skip(f"Lamar Jackson data not available: {result.get('error')}")
            return

        data = result["data"]
        assert data["position"] == "QB"
        assert data["games"] >= 16  # At least 16 regular season games
        assert data["fantasy_points"] > 0

    def test_get_fantasy_player_summary_james_cook_2024(self):
        """Test James Cook 2024 fantasy summary."""
        result = get_fantasy_player_summary("James Cook", 2024, scoring="ppr")

        assert result["ok"] == True
        assert result["data"] is not None
        data = result["data"]

        assert data["name"] == "James Cook"
        assert data["position"] == "RB"
        assert data["team"] == "BUF"
        assert data["carries"] > 0
        assert data["rushing_yards"] > 0
        assert data["fantasy_points"] > 0

    def test_get_fantasy_player_summary_invalid_scoring(self):
        """Test invalid scoring format."""
        result = get_fantasy_player_summary("Josh Allen", 2024, scoring="invalid")

        assert result["ok"] == False
        assert "Invalid scoring format" in result["error"]

    def test_get_fantasy_player_summary_invalid_player(self):
        """Test invalid player name."""
        result = get_fantasy_player_summary("Nonexistent Player", 2024, scoring="ppr")

        assert result["ok"] == False

    def test_get_fantasy_player_summary_half_ppr(self):
        """Test half-PPR scoring."""
        result = get_fantasy_player_summary("Josh Allen", 2024, scoring="half_ppr")

        assert result["ok"] == True
        assert result["data"]["scoring"] == "half_ppr"
        assert result["meta"]["scoring_format"] == "half_ppr"

    def test_get_fantasy_player_summary_standard(self):
        """Test standard scoring."""
        result = get_fantasy_player_summary("Josh Allen", 2024, scoring="standard")

        assert result["ok"] == True
        assert result["data"]["scoring"] == "standard"
        assert result["meta"]["scoring_format"] == "standard"

    def test_get_fantasy_player_summary_2025_marked_pbp_derived(self):
        """Test that 2025 player data is marked as pbp_derived."""
        # This may fail if 2025 data isn't available, but the important
        # test is that IF it returns ok=true, it marks source correctly
        result = get_fantasy_player_summary("Josh Allen", 2025, scoring="ppr")

        if result["ok"]:
            assert result["meta"]["source"] == "pbp_derived"
            assert "2025_note" in result["meta"]


class TestCompareFantasyPlayers:
    """Test compare_fantasy_players function."""

    def test_compare_fantasy_players_two_qbs(self):
        """Test comparing two QBs."""
        result = compare_fantasy_players(
            ["Josh Allen", "Lamar Jackson"], 2024, scoring="ppr"
        )

        assert result["ok"] == True
        assert result["data"] is not None
        assert len(result["data"]) >= 1  # At least Josh Allen

        # Check structure for successful players
        for player in result["data"]:
            assert "name" in player
            if "error" not in player:  # Valid player
                assert "position" in player
                assert "fantasy_points" in player

        # Meta check
        assert result["meta"]["season"] == 2024
        assert result["meta"]["scoring_format"] == "ppr"

    def test_compare_fantasy_players_mixed_positions(self):
        """Test comparing players of different positions."""
        result = compare_fantasy_players(
            ["Josh Allen", "James Cook", "Khalil Shakir"], 2024, scoring="ppr"
        )

        assert result["ok"] == True
        assert len(result["data"]) == 3

    def test_compare_fantasy_players_invalid_scoring(self):
        """Test invalid scoring format in comparison."""
        result = compare_fantasy_players(
            ["Josh Allen", "Lamar Jackson"], 2024, scoring="invalid"
        )

        assert result["ok"] == False
        assert "Invalid scoring format" in result["error"]

    def test_compare_fantasy_players_empty_list(self):
        """Test empty player list."""
        result = compare_fantasy_players([], 2024, scoring="ppr")

        assert result["ok"] == False
        assert "cannot be empty" in result["error"].lower()

    def test_compare_fantasy_players_half_ppr(self):
        """Test comparison with half-PPR scoring."""
        result = compare_fantasy_players(
            ["Josh Allen", "Lamar Jackson"], 2024, scoring="half_ppr"
        )

        assert result["ok"] == True
        assert result["meta"]["scoring_format"] == "half_ppr"
        assert all(p["scoring"] == "half_ppr" for p in result["data"] if "scoring" in p)


class TestPlayerWeeklyUsage:
    """Test get_player_weekly_usage function."""

    def test_get_player_weekly_usage_josh_allen_2024(self):
        """Test Josh Allen's weekly usage in 2024."""
        result = get_player_weekly_usage("Josh Allen", 2024)

        # Weekly data might not be available in all schemas, skip if not found
        if not result["ok"]:
            pytest.skip(f"Weekly usage data not available: {result.get('error')}")
            return

        assert result["data"] is not None
        assert len(result["data"]) > 0

        # Check structure of weekly data
        for week_data in result["data"]:
            assert "week" in week_data
            assert "carries" in week_data
            assert "targets" in week_data
            assert "receptions" in week_data

        # Meta check
        assert result["meta"]["name"] == "Josh Allen"
        assert result["meta"]["position"] == "QB"

    def test_get_player_weekly_usage_james_cook_2024(self):
        """Test James Cook's weekly usage in 2024."""
        result = get_player_weekly_usage("James Cook", 2024)

        if not result["ok"]:
            pytest.skip(f"Weekly usage data not available: {result.get('error')}")
            return

        assert result["data"] is not None
        assert len(result["data"]) > 0

        # RB should have carries and targets
        for week in result["data"]:
            # At least some weeks should have carries or targets
            if week["carries"] > 0 or week["targets"] > 0:
                assert week["fantasy_points_ppr"] >= 0

    def test_get_player_weekly_usage_khalil_shakir_2024(self):
        """Test Khalil Shakir's weekly usage in 2024."""
        result = get_player_weekly_usage("Khalil Shakir", 2024)

        if not result["ok"]:
            pytest.skip(f"Weekly usage data not available: {result.get('error')}")
            return

        assert result["data"] is not None
        # WR should have targets
        assert any(w["targets"] > 0 for w in result["data"])

    def test_get_player_weekly_usage_invalid_player(self):
        """Test invalid player name."""
        result = get_player_weekly_usage("Nonexistent Player", 2024)

        assert result["ok"] == False

    def test_get_player_weekly_usage_2025(self):
        """Test 2025 player weekly usage is marked pbp_derived if available."""
        result = get_player_weekly_usage("Josh Allen", 2025)

        if result["ok"]:
            assert result["meta"]["source"] == "pbp_derived"
            assert "2025_note" in result["meta"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
