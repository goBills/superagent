"""
Tests for CLI formatting functions.

Tests that CLI functions properly format agent/tool output for display.
"""

import sys
from pathlib import Path

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from superagent.cli import (
    format_team_summary,
    format_player_summary,
    format_player_comparison,
    format_epa_trend,
    format_agent_response,
)


class TestFormatTeamSummary:
    """Test team summary formatting."""

    def test_format_team_summary_basic(self):
        """Test formatting of basic team summary."""
        data = {
            "team": "BUF",
            "season": 2024,
            "games": 17,
            "wins": 13,
            "losses": 4,
            "points_for": 525,
            "points_against": 368,
            "offensive_epa": 123.45,
            "offensive_epa_per_play": 0.15,
            "defensive_epa_allowed": -98.76,
            "defensive_epa_per_play_allowed": -0.12,
            "avg_offensive_yards": 354.2,
            "play_count": 1024,
        }

        result = format_team_summary(data)

        # Check that key values are in the output
        assert "BUF" in result
        assert "2024" in result
        assert "13-4" in result
        assert "525" in result
        assert result  # Non-empty

    def test_format_team_summary_empty(self):
        """Test formatting with empty data."""
        result = format_team_summary({})
        assert "No data available" in result or result == ""

    def test_format_team_summary_none(self):
        """Test formatting with None."""
        result = format_team_summary(None)
        assert "No data available" in result or result == ""


class TestFormatPlayerSummary:
    """Test player summary formatting."""

    def test_format_player_summary_qb(self):
        """Test formatting of QB player summary."""
        data = {
            "player_id": "test_id",
            "name": "Josh Allen",
            "position": "QB",
            "team": "BUF",
            "season": 2024,
            "games": 17,
            "passing_attempts": 651,
            "completions": 420,
            "completion_pct": 0.646,
            "passing_yards": 4367,
            "passing_tds": 32,
            "interceptions": 6,
            "carries": 105,
            "rushing_yards": 531,
            "rushing_tds": 3,
            "targets": 0,
            "receptions": 0,
            "receiving_yards": 0,
            "receiving_tds": 0,
        }

        result = format_player_summary(data)

        # Check key values
        assert "Josh Allen" in result
        assert "QB" in result
        assert "BUF" in result
        assert "4367" in result
        assert "32" in result
        assert result

    def test_format_player_summary_wr(self):
        """Test formatting of WR player summary."""
        data = {
            "player_id": "test_id",
            "name": "Stefon Diggs",
            "position": "WR",
            "team": "BUF",
            "season": 2024,
            "games": 13,
            "passing_attempts": 0,
            "completions": 0,
            "passing_yards": 0,
            "passing_tds": 0,
            "interceptions": 0,
            "carries": 0,
            "rushing_yards": 0,
            "rushing_tds": 0,
            "targets": 110,
            "receptions": 85,
            "receiving_yards": 960,
            "receiving_tds": 5,
        }

        result = format_player_summary(data)

        # Check key values
        assert "Stefon Diggs" in result
        assert "WR" in result
        assert "110" in result
        assert "85" in result
        assert result


class TestFormatPlayerComparison:
    """Test player comparison formatting."""

    def test_format_player_comparison_two_players(self):
        """Test formatting of two-player comparison."""
        data = [
            {
                "player_id": "id1",
                "name": "Josh Allen",
                "position": "QB",
                "team": "BUF",
                "passing_yards": 4367,
                "passing_tds": 32,
            },
            {
                "player_id": "id2",
                "name": "Lamar Jackson",
                "position": "QB",
                "team": "BAL",
                "passing_yards": 4172,
                "passing_tds": 41,
            },
        ]

        result = format_player_comparison(data)

        # Check for player names and key stats
        assert "Josh Allen" in result
        assert "Lamar Jackson" in result
        assert result

    def test_format_player_comparison_empty(self):
        """Test formatting with empty data."""
        result = format_player_comparison([])
        assert "No data available" in result or result == ""


class TestFormatEpaTrend:
    """Test EPA trend formatting."""

    def test_format_epa_trend_weeks(self):
        """Test formatting of EPA trend over weeks."""
        data = [
            {
                "week": 1,
                "offensive_epa": 0.15,
                "defensive_epa_allowed": -0.10,
                "net_epa": 0.25,
                "play_count": 60,
            },
            {
                "week": 2,
                "offensive_epa": 0.18,
                "defensive_epa_allowed": -0.12,
                "net_epa": 0.30,
                "play_count": 62,
            },
        ]

        result = format_epa_trend(data)

        # Check for weeks and EPA values
        assert "Week 1" in result
        assert "Week 2" in result
        assert result

    def test_format_epa_trend_empty(self):
        """Test formatting with empty data."""
        result = format_epa_trend([])
        assert "No data available" in result or result == ""


class TestFormatAgentResponse:
    """Test agent response formatting."""

    def test_format_agent_response_success(self):
        """Test formatting of successful agent response."""
        result_dict = {
            "ok": True,
            "answer": "The Bills went 13-4 in 2024.",
            "tools_used": [
                {
                    "name": "get_team_summary",
                    "input": {"team": "BUF", "season": 2024},
                    "result": {"ok": True},
                }
            ],
            "raw_response": {},
        }

        result = format_agent_response(result_dict)

        # Check for answer and tool used
        assert "13-4" in result
        assert "get_team_summary" in result
        assert "✅" in result or "ok" in result.lower()

    def test_format_agent_response_error(self):
        """Test formatting of error response."""
        result_dict = {
            "ok": False,
            "answer": None,
            "tools_used": [],
            "error": "Invalid team name",
        }

        result = format_agent_response(result_dict)

        assert "Error" in result or "error" in result.lower()
        assert "Invalid team name" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
