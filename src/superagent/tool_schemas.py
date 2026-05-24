"""
Claude tool schemas for Superagent deterministic tools.

Defines JSON schemas that Claude understands, plus a dispatch map
to route tool calls to Python functions.
"""

from typing import Dict, Any, Callable
from superagent.tools import (
    get_team_summary,
    get_player_summary,
    compare_players,
    get_team_epa_trend,
)


TOOL_SCHEMAS = [
    {
        "name": "get_team_summary",
        "description": "Get a team's season summary: wins, losses, points, EPA metrics",
        "input_schema": {
            "type": "object",
            "properties": {
                "team": {
                    "type": "string",
                    "description": "Team name or abbreviation (e.g., 'Bills', 'BUF', 'Buffalo')"
                },
                "season": {
                    "type": "integer",
                    "description": "NFL season year (2020-2025)"
                }
            },
            "required": ["team", "season"]
        }
    },
    {
        "name": "get_player_summary",
        "description": "Get a player's season stats: position, team, passing/rushing/receiving stats, EPA metrics",
        "input_schema": {
            "type": "object",
            "properties": {
                "player_name": {
                    "type": "string",
                    "description": "Player's full name (e.g., 'Josh Allen', 'Lamar Jackson')"
                },
                "season": {
                    "type": "integer",
                    "description": "NFL season year (2020-2025)"
                }
            },
            "required": ["player_name", "season"]
        }
    },
    {
        "name": "compare_players",
        "description": "Compare multiple players' stats side-by-side for a season",
        "input_schema": {
            "type": "object",
            "properties": {
                "player_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of player names to compare (e.g., ['Josh Allen', 'Lamar Jackson'])"
                },
                "season": {
                    "type": "integer",
                    "description": "NFL season year (2020-2025)"
                },
                "metrics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of specific metrics to include (e.g., ['passing_yards', 'passing_tds']). If omitted, includes all available stats.",
                    "default": None
                }
            },
            "required": ["player_names", "season"]
        }
    },
    {
        "name": "get_team_epa_trend",
        "description": "Get a team's EPA (Expected Points Added) trend over a range of weeks in a season",
        "input_schema": {
            "type": "object",
            "properties": {
                "team": {
                    "type": "string",
                    "description": "Team name or abbreviation (e.g., 'Bills', 'BUF')"
                },
                "season": {
                    "type": "integer",
                    "description": "NFL season year (2020-2025)"
                },
                "start_week": {
                    "type": "integer",
                    "description": "Starting week (1-17)"
                },
                "end_week": {
                    "type": "integer",
                    "description": "Ending week (1-17, inclusive)"
                }
            },
            "required": ["team", "season", "start_week", "end_week"]
        }
    }
]


TOOL_DISPATCH: Dict[str, Callable] = {
    "get_team_summary": get_team_summary,
    "get_player_summary": get_player_summary,
    "compare_players": compare_players,
    "get_team_epa_trend": get_team_epa_trend,
}


def get_tool_by_name(name: str) -> Callable:
    """Get a tool function by name. Raises KeyError if not found."""
    return TOOL_DISPATCH[name]


def tool_schema_for_claude() -> list[Dict[str, Any]]:
    """Return tool schemas formatted for Claude API."""
    return TOOL_SCHEMAS
