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
    get_player_advanced_summary,
    compare_player_advanced,
    get_team_schedule_context,
    get_bye_weeks,
    get_upcoming_games,
    get_fantasy_schedule_context,
    compare_fantasy_context,
)
from superagent.draft_tools import (
    find_draft_targets,
    compare_draft_options,
    get_draft_context,
    get_bye_week_analysis,
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
    },
    {
        "name": "get_player_advanced_summary",
        "description": "Get a player's EPA, success rate, CPOE, and position-specific advanced metrics from nflverse play-by-play.",
        "input_schema": {
            "type": "object",
            "properties": {
                "player_name": {
                    "type": "string",
                    "description": "Player's full name (e.g., 'Josh Allen', 'James Cook', 'Khalil Shakir')"
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
        "name": "compare_player_advanced",
        "description": "Compare multiple players using EPA/play, success rate, CPOE, and position-relevant advanced metrics.",
        "input_schema": {
            "type": "object",
            "properties": {
                "player_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of player names to compare"
                },
                "season": {
                    "type": "integer",
                    "description": "NFL season year (2020-2025)"
                },
                "metrics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional metrics to include, such as epa_per_play, success_rate, cpoe, rushing_epa_per_attempt, receiving_epa_per_target",
                    "default": None
                }
            },
            "required": ["player_names", "season"]
        }
    },
    {
        "name": "get_team_schedule_context",
        "description": "Get a team's full season schedule with game dates, opponents, locations, and results. Includes bye week.",
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
                }
            },
            "required": ["team", "season"]
        }
    },
    {
        "name": "get_bye_weeks",
        "description": "Get bye weeks for a season. If team is specified, returns that team's bye week. Otherwise returns all teams' bye weeks.",
        "input_schema": {
            "type": "object",
            "properties": {
                "season": {
                    "type": "integer",
                    "description": "NFL season year (2020-2025)"
                },
                "team": {
                    "type": "string",
                    "description": "Optional team name or abbreviation. If provided, returns only that team's bye week."
                }
            },
            "required": ["season"]
        }
    },
    {
        "name": "get_upcoming_games",
        "description": "Get a team's games from a specified week onward. Useful for analyzing schedule difficulty from a point forward.",
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
                "from_week": {
                    "type": "integer",
                    "description": "Starting week (default: 1). Games from this week onward."
                }
            },
            "required": ["team", "season"]
        }
    },
    {
        "name": "get_fantasy_schedule_context",
        "description": "Get a player's fantasy schedule context: team bye week, games from a selected week, weekly usage, and usage trend. Does NOT include injuries, depth charts, or projections.",
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
                "from_week": {
                    "type": "integer",
                    "description": "Optional starting week (default: 1). Games from this week onward."
                }
            },
            "required": ["player_name", "season"]
        }
    },
    {
        "name": "compare_fantasy_context",
        "description": "Compare multiple players' fantasy schedule context side-by-side: bye weeks, games from a selected week, and usage trends.",
        "input_schema": {
            "type": "object",
            "properties": {
                "player_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of player names (e.g., ['James Cook', 'Khalil Shakir'])"
                },
                "season": {
                    "type": "integer",
                    "description": "NFL season year (2020-2025)"
                },
                "from_week": {
                    "type": "integer",
                    "description": "Optional starting week (default: 1)."
                }
            },
            "required": ["player_names", "season"]
        }
    },
    {
        "name": "find_draft_targets",
        "description": "Find available draft targets for a stored league using imported draft market data and league settings. Historical decision support, not a projection.",
        "input_schema": {
            "type": "object",
            "properties": {
                "league_id": {"type": "integer", "description": "Stored Superagent league id"},
                "position": {"type": "string", "description": "Optional position filter: QB, RB, WR, TE, K, DST"},
                "min_effective_rank": {
                    "type": "number",
                    "description": "Optional minimum Effective Rank to include, useful for 'after pick 70'. Effective Rank uses ADP when available, otherwise avg rank, otherwise overall rank."
                },
                "max_effective_rank": {
                    "type": "number",
                    "description": "Optional maximum Effective Rank to include. Effective Rank uses ADP when available, otherwise avg rank, otherwise overall rank."
                },
                "min_adp": {
                    "type": "number",
                    "description": "Backward-compatible alias for min_effective_rank."
                },
                "max_adp": {
                    "type": "number",
                    "description": "Backward-compatible alias for max_effective_rank."
                },
                "min_value_delta": {"type": "number", "description": "Optional minimum value delta"},
                "bye_week_filters": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Optional bye weeks to exclude"
                },
                "season": {"type": "integer", "description": "Draft season"},
                "source": {"type": "string", "description": "Optional market source, e.g. draftsheetsv6"},
                "limit": {"type": "integer", "description": "Maximum rows to return"}
            },
            "required": ["league_id"]
        }
    },
    {
        "name": "compare_draft_options",
        "description": "Compare specific players as draft options in a stored league context using imported market data and league settings.",
        "input_schema": {
            "type": "object",
            "properties": {
                "league_id": {"type": "integer", "description": "Stored Superagent league id"},
                "player_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Player names to compare"
                },
                "season": {"type": "integer", "description": "Draft season"},
                "source": {"type": "string", "description": "Optional market source, e.g. draftsheetsv6"}
            },
            "required": ["league_id", "player_names"]
        }
    },
    {
        "name": "get_draft_context",
        "description": "Summarize a stored league's draft settings, recent picks, drafted count, and top available values.",
        "input_schema": {
            "type": "object",
            "properties": {
                "league_id": {"type": "integer", "description": "Stored Superagent league id"},
                "drafted_player_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional extra canonical player ids already drafted"
                },
                "season": {"type": "integer", "description": "Draft season"},
                "source": {"type": "string", "description": "Optional market source, e.g. draftsheetsv6"}
            },
            "required": ["league_id"]
        }
    },
    {
        "name": "get_bye_week_analysis",
        "description": "Analyze bye-week concentration for players already drafted or selected in a league.",
        "input_schema": {
            "type": "object",
            "properties": {
                "league_id": {"type": "integer", "description": "Stored Superagent league id"},
                "picked_so_far": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional canonical player ids already picked"
                },
                "season": {"type": "integer", "description": "Draft season"},
                "source": {"type": "string", "description": "Optional market source, e.g. draftsheetsv6"}
            },
            "required": ["league_id"]
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
    "get_player_advanced_summary": get_player_advanced_summary,
    "compare_player_advanced": compare_player_advanced,
    "get_team_schedule_context": get_team_schedule_context,
    "get_bye_weeks": get_bye_weeks,
    "get_upcoming_games": get_upcoming_games,
    "get_fantasy_schedule_context": get_fantasy_schedule_context,
    "compare_fantasy_context": compare_fantasy_context,
    "find_draft_targets": find_draft_targets,
    "compare_draft_options": compare_draft_options,
    "get_draft_context": get_draft_context,
    "get_bye_week_analysis": get_bye_week_analysis,
}


def get_tool_by_name(name: str) -> Callable:
    """Get a tool function by name. Raises KeyError if not found."""
    return TOOL_DISPATCH[name]


def tool_schema_for_claude() -> list[Dict[str, Any]]:
    """Return tool schemas formatted for Claude API."""
    return TOOL_SCHEMAS
