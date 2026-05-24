"""
Tests for Phase 4B: historical draft research tools.

These are deterministic research filters over existing weekly/fantasy data.
They do not test projections, start/sit advice, or live waiver recommendations.
"""

import sys
from pathlib import Path

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from superagent.tool_schemas import TOOL_DISPATCH, TOOL_SCHEMAS
from superagent.tools import (
    find_late_season_breakouts,
    find_target_opportunity_players,
    find_usage_risers,
)


class TestUsageRisers:
    """Test find_usage_risers."""

    def test_find_usage_risers_rb_2024(self):
        result = find_usage_risers("RB", 2024, 1, 17)

        assert result["ok"] == True
        assert result["data"]
        assert result["meta"]["position"] == "RB"
        assert result["meta"]["early_weeks"] == "1-8"
        assert result["meta"]["late_weeks"] == "9-17"

        deltas = [row["change"]["opportunities_per_game_delta"] for row in result["data"]]
        assert deltas == sorted(deltas, reverse=True)

        names = {row["name"] for row in result["data"]}
        assert "Chase Brown" in names

        for row in result["data"]:
            assert row["position"] == "RB"
            assert row["early"]["opportunities"] >= 10
            assert row["late"]["opportunities"] >= 15
            assert row["change"]["opportunities_per_game_delta"] >= 3.0
            assert row["change"]["ppr_points_per_game_delta"] >= 3.0

    def test_find_usage_risers_wr_2024(self):
        result = find_usage_risers("WR", 2024, 1, 17)

        assert result["ok"] == True
        assert result["data"]
        assert all(row["position"] == "WR" for row in result["data"])
        assert all(row["late"]["opportunities"] >= 15 for row in result["data"])

    def test_find_usage_risers_invalid_position(self):
        result = find_usage_risers("PUNTER", 2024, 1, 17)

        assert result["ok"] == False
        assert "Unsupported position" in result["error"]

    def test_find_usage_risers_invalid_week_range(self):
        result = find_usage_risers("RB", 2024, 17, 1)

        assert result["ok"] == False
        assert "valid week range" in result["error"]


class TestTargetOpportunity:
    """Test find_target_opportunity_players."""

    def test_find_target_opportunity_wr_2024(self):
        result = find_target_opportunity_players(2024, 100, "WR")

        assert result["ok"] == True
        assert result["data"]
        assert result["meta"]["position"] == "WR"
        assert result["meta"]["min_targets"] == 100

        target_shares = [row["target_share"] for row in result["data"]]
        assert target_shares == sorted(target_shares, reverse=True)

        names = {row["name"] for row in result["data"]}
        assert "Malik Nabers" in names
        assert "Ja'Marr Chase" in names

        for row in result["data"]:
            assert row["position"] == "WR"
            assert row["targets"] >= 100
            assert 0 <= row["target_share"] <= 1
            assert row["targets_per_game"] > 0

    def test_find_target_opportunity_te_2024(self):
        result = find_target_opportunity_players(2024, 75, "TE")

        assert result["ok"] == True
        assert result["data"]
        assert all(row["position"] == "TE" for row in result["data"])
        assert all(row["targets"] >= 75 for row in result["data"])

    def test_find_target_opportunity_without_position_excludes_qbs(self):
        result = find_target_opportunity_players(2024, 120)

        assert result["ok"] == True
        assert result["data"]
        assert all(row["position"] != "QB" for row in result["data"])

    def test_find_target_opportunity_2025_pbp_derived(self):
        result = find_target_opportunity_players(2025, 80, "WR")

        assert result["ok"] == True
        assert result["meta"]["source"] == "pbp_derived"
        assert "2025_note" in result["meta"]
        assert result["data"]

    def test_find_target_opportunity_invalid_min_targets(self):
        result = find_target_opportunity_players(2024, 0, "WR")

        assert result["ok"] == False
        assert "min_targets" in result["error"]

    def test_find_target_opportunity_empty_result(self):
        result = find_target_opportunity_players(2024, 1000, "WR")

        assert result["ok"] == True
        assert result["data"] == []


class TestLateSeasonBreakouts:
    """Test find_late_season_breakouts."""

    def test_find_late_season_breakouts_rb_2024(self):
        result = find_late_season_breakouts("RB", 2024)

        assert result["ok"] == True
        assert result["data"]
        assert result["meta"]["early_weeks"] == "1-8"
        assert result["meta"]["late_weeks"] == "9-17"

        ppr_deltas = [row["change"]["ppr_points_per_game_delta"] for row in result["data"]]
        assert ppr_deltas == sorted(ppr_deltas, reverse=True)

        names = {row["name"] for row in result["data"]}
        assert "Chase Brown" in names

        for row in result["data"]:
            assert row["position"] == "RB"
            assert row["change"]["opportunities_per_game_delta"] >= 3.0
            assert row["change"]["ppr_points_per_game_delta"] >= 3.0

    def test_find_late_season_breakouts_wr_2024(self):
        result = find_late_season_breakouts("WR", 2024)

        assert result["ok"] == True
        assert result["data"]
        assert all(row["position"] == "WR" for row in result["data"])

    def test_find_late_season_breakouts_invalid_position(self):
        result = find_late_season_breakouts("EDGE", 2024)

        assert result["ok"] == False
        assert "Unsupported position" in result["error"]


class TestDraftResearchToolSchemas:
    """Test Claude schema integration for Phase 4B tools."""

    @pytest.mark.parametrize(
        "tool_name",
        [
            "find_usage_risers",
            "find_target_opportunity_players",
            "find_late_season_breakouts",
        ],
    )
    def test_draft_research_tools_are_in_dispatch(self, tool_name):
        assert tool_name in TOOL_DISPATCH
        assert callable(TOOL_DISPATCH[tool_name])

    @pytest.mark.parametrize(
        "tool_name",
        [
            "find_usage_risers",
            "find_target_opportunity_players",
            "find_late_season_breakouts",
        ],
    )
    def test_draft_research_tools_have_schemas(self, tool_name):
        schema_names = {schema["name"] for schema in TOOL_SCHEMAS}
        assert tool_name in schema_names
