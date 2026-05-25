"""
Tests for Phase 5: player EPA and advanced analytics.
"""

import sys
from pathlib import Path

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from superagent.tool_schemas import TOOL_DISPATCH, TOOL_SCHEMAS
from superagent.tools import compare_player_advanced, get_player_advanced_summary


class TestPlayerAdvancedSummary:
    """Test get_player_advanced_summary."""

    def test_josh_allen_2024_qb_advanced(self):
        result = get_player_advanced_summary("Josh Allen", 2024)

        assert result["ok"] == True
        data = result["data"]
        assert data["name"] == "Josh Allen"
        assert data["position"] == "QB"
        assert data["team"] == "BUF"
        assert data["plays_analyzed"] > 500

        passing = data["passing"]
        assert passing["pass_plays"] > 500
        assert passing["passing_epa_per_play"] is not None
        assert passing["qb_epa_per_play"] is not None
        assert passing["pass_success_rate"] is not None
        assert passing["cpoe"] is not None
        assert passing["cp"] is not None

        scrambles = data["scrambles"]
        assert scrambles["scrambles"] > 5
        assert scrambles["scramble_epa_per_play"] is not None

        primary = data["primary_metrics"]
        assert primary["epa_per_play"] == passing["qb_epa_per_play"]
        assert primary["success_rate"] == passing["pass_success_rate"]
        assert primary["cpoe"] == passing["cpoe"]

        assert result["meta"]["source"] == "plays"
        assert result["meta"]["minimum_sample_for_rates"] == 5
        assert "nflverse" in result["meta"]["epa_source"]

    def test_james_cook_2024_rb_advanced(self):
        result = get_player_advanced_summary("James Cook", 2024)

        assert result["ok"] == True
        data = result["data"]
        assert data["name"] == "James Cook"
        assert data["position"] == "RB"
        assert data["team"] == "BUF"

        rushing = data["rushing"]
        receiving = data["receiving"]
        assert rushing["rush_attempts"] > 100
        assert rushing["rushing_epa_per_attempt"] is not None
        assert receiving["targets"] > 20
        assert receiving["receiving_epa_per_target"] is not None
        assert data["total_opportunities"] == rushing["rush_attempts"] + receiving["targets"]
        assert data["total_epa_per_opportunity"] is not None

        primary = data["primary_metrics"]
        assert primary["epa_per_play"] == data["total_epa_per_opportunity"]
        assert primary["rushing_epa_per_attempt"] == rushing["rushing_epa_per_attempt"]
        assert primary["receiving_epa_per_target"] == receiving["receiving_epa_per_target"]

    def test_khalil_shakir_2024_wr_advanced(self):
        result = get_player_advanced_summary("Khalil Shakir", 2024)

        assert result["ok"] == True
        data = result["data"]
        assert data["name"] == "Khalil Shakir"
        assert data["position"] == "WR"

        receiving = data["receiving"]
        assert receiving["targets"] > 50
        assert receiving["receiving_epa_per_target"] is not None
        assert receiving["air_epa_per_target"] is not None
        assert receiving["yac_epa_per_target"] is not None
        assert receiving["xyac_epa_per_target"] is not None
        assert receiving["receiving_success_rate"] is not None

        rushing = data["rushing"]
        if rushing["rush_attempts"] < 5:
            assert rushing["rushing_epa_per_attempt"] is None
            assert "sample_note" in rushing

    def test_2025_advanced_marked_with_note(self):
        result = get_player_advanced_summary("Josh Allen", 2025)

        assert result["ok"] == True
        assert result["meta"]["source"] == "plays"
        assert "2025_note" in result["meta"]
        assert result["data"]["passing"]["pass_plays"] > 0

    def test_small_sample_category_returns_null_rates(self):
        result = get_player_advanced_summary("Khalil Shakir", 2024)

        assert result["ok"] == True
        rushing = result["data"]["rushing"]
        assert rushing["rush_attempts"] < 5
        assert rushing["rushing_epa_per_attempt"] is None
        assert rushing["rush_success_rate"] is None
        assert "sample_note" in rushing

    def test_invalid_player(self):
        result = get_player_advanced_summary("Not A Real Player", 2024)

        assert result["ok"] == False
        assert result["error"]


class TestComparePlayerAdvanced:
    """Test compare_player_advanced."""

    def test_compare_two_qbs_default_metrics(self):
        result = compare_player_advanced(["Josh Allen", "Lamar Jackson"], 2024)

        assert result["ok"] == True
        assert len(result["data"]) == 2
        assert result["meta"]["metrics"] == ["epa_per_play", "success_rate", "cpoe"]
        assert result["meta"]["players_compared"] == 2

        names = {row["name"] for row in result["data"]}
        assert names == {"Josh Allen", "Lamar Jackson"}
        for row in result["data"]:
            assert row["position"] == "QB"
            assert row["epa_per_play"] is not None
            assert row["success_rate"] is not None
            assert row["cpoe"] is not None

    def test_compare_custom_metrics_mixed_positions(self):
        result = compare_player_advanced(
            ["James Cook", "Khalil Shakir"],
            2024,
            ["epa_per_play", "success_rate", "receiving_epa_per_target"],
        )

        assert result["ok"] == True
        assert len(result["data"]) == 2
        assert result["meta"]["metrics"] == [
            "epa_per_play",
            "success_rate",
            "receiving_epa_per_target",
        ]
        for row in result["data"]:
            assert "receiving_epa_per_target" in row

    def test_compare_empty_list(self):
        result = compare_player_advanced([], 2024)

        assert result["ok"] == False
        assert "cannot be empty" in result["error"]

    def test_compare_with_invalid_player_preserves_error_row(self):
        result = compare_player_advanced(["Josh Allen", "Not A Real Player"], 2024)

        assert result["ok"] == True
        assert len(result["data"]) == 2
        assert any(row.get("error") for row in result["data"])
        assert result["meta"]["players_compared"] == 1


class TestAdvancedToolSchemas:
    """Test Claude schema integration for advanced tools."""

    @pytest.mark.parametrize(
        "tool_name",
        ["get_player_advanced_summary", "compare_player_advanced"],
    )
    def test_advanced_tools_are_in_dispatch(self, tool_name):
        assert tool_name in TOOL_DISPATCH
        assert callable(TOOL_DISPATCH[tool_name])

    @pytest.mark.parametrize(
        "tool_name",
        ["get_player_advanced_summary", "compare_player_advanced"],
    )
    def test_advanced_tools_have_schemas(self, tool_name):
        schema_names = {schema["name"] for schema in TOOL_SCHEMAS}
        assert tool_name in schema_names
