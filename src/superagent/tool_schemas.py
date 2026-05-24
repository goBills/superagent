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
    get_fantasy_player_summary,
    compare_fantasy_players,
    get_player_weekly_usage,
    find_usage_risers,
    find_target_opportunity_players,
    find_late_season_breakouts,
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
    },
    {
        "name": "get_fantasy_player_summary",
        "description": "Get a player's fantasy stats for a season: games, fantasy points, PPR/half-PPR/standard scoring, targets, receptions, yards, TDs",
        "input_schema": {
            "type": "object",
            "properties": {
                "player_name": {
                    "type": "string",
                    "description": "Player's full name (e.g., 'Josh Allen', 'James Cook')"
                },
                "season": {
                    "type": "integer",
                    "description": "NFL season year (2020-2025)"
                },
                "scoring": {
                    "type": "string",
                    "description": "Scoring format: 'standard', 'half_ppr', or 'ppr' (default: 'ppr')",
                    "enum": ["standard", "half_ppr", "ppr"],
                    "default": "ppr"
                }
            },
            "required": ["player_name", "season"]
        }
    },
    {
        "name": "compare_fantasy_players",
        "description": "Compare multiple players' fantasy stats side-by-side with fantasy points and scoring breakdown",
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
                "scoring": {
                    "type": "string",
                    "description": "Scoring format: 'standard', 'half_ppr', or 'ppr' (default: 'ppr')",
                    "enum": ["standard", "half_ppr", "ppr"],
                    "default": "ppr"
                }
            },
            "required": ["player_names", "season"]
        }
    },
    {
        "name": "get_player_weekly_usage",
        "description": "Get a player's weekly usage stats (carries, targets, receptions, yards, TDs, fantasy points) for each week of a season",
        "input_schema": {
            "type": "object",
            "properties": {
                "player_name": {
                    "type": "string",
                    "description": "Player's full name (e.g., 'Josh Allen', 'James Cook')"
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
        "name": "find_usage_risers",
        "description": "Find historical fantasy draft research candidates whose opportunities and PPR points rose across a week range. This is research, not a projection.",
        "input_schema": {
            "type": "object",
            "properties": {
                "position": {
                    "type": "string",
                    "description": "Fantasy position to search: RB, WR, TE, QB, or K",
                    "enum": ["RB", "WR", "TE", "QB", "K"]
                },
                "season": {
                    "type": "integer",
                    "description": "NFL season year (2020-2025)"
                },
                "start_week": {
                    "type": "integer",
                    "description": "Start of the full comparison window"
                },
                "end_week": {
                    "type": "integer",
                    "description": "End of the full comparison window"
                }
            },
            "required": ["position", "season", "start_week", "end_week"]
        }
    },
    {
        "name": "find_target_opportunity_players",
        "description": "Find players with at least a target threshold and their team target share. Useful for historical draft research, not projections.",
        "input_schema": {
            "type": "object",
            "properties": {
                "season": {
                    "type": "integer",
                    "description": "NFL season year (2020-2025)"
                },
                "min_targets": {
                    "type": "integer",
                    "description": "Minimum season targets to include"
                },
                "position": {
                    "type": "string",
                    "description": "Optional position filter: RB, WR, TE, QB, K, or ALL",
                    "enum": ["RB", "WR", "TE", "QB", "K", "ALL"]
                }
            },
            "required": ["season", "min_targets"]
        }
    },
    {
        "name": "find_late_season_breakouts",
        "description": "Find players whose opportunities and PPR points improved from weeks 1-8 to weeks 9-17. Historical research only, not a prediction.",
        "input_schema": {
            "type": "object",
            "properties": {
                "position": {
                    "type": "string",
                    "description": "Fantasy position to search: RB, WR, TE, QB, or K",
                    "enum": ["RB", "WR", "TE", "QB", "K"]
                },
                "season": {
                    "type": "integer",
                    "description": "NFL season year (2020-2025)"
                }
            },
            "required": ["position", "season"]
        }
    }
]


TOOL_DISPATCH: Dict[str, Callable] = {
    "get_team_summary": get_team_summary,
    "get_player_summary": get_player_summary,
    "compare_players": compare_players,
    "get_team_epa_trend": get_team_epa_trend,
    "get_fantasy_player_summary": get_fantasy_player_summary,
    "compare_fantasy_players": compare_fantasy_players,
    "get_player_weekly_usage": get_player_weekly_usage,
    "find_usage_risers": find_usage_risers,
    "find_target_opportunity_players": find_target_opportunity_players,
    "find_late_season_breakouts": find_late_season_breakouts,
}


def get_tool_by_name(name: str) -> Callable:
    """Get a tool function by name. Raises KeyError if not found."""
    return TOOL_DISPATCH[name]


def tool_schema_for_claude() -> list[Dict[str, Any]]:
    """Return tool schemas formatted for Claude API."""
    return TOOL_SCHEMAS
