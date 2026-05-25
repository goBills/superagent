"""
Deterministic query tools for Superagent.

Core tools that return structured JSON-safe results.
All tools follow the output contract:
    {
        "ok": bool,
        "data": dict | list | None,
        "error": str | None,
        "meta": dict
    }
"""

from typing import Dict, List, Any, Optional
import duckdb
from superagent.config import get_config
from superagent.name_resolution import resolve_team, resolve_player
from superagent.db_query import get_db_connection, get_player_stats

config = get_config()


def get_team_summary(team: str, season: int) -> Dict[str, Any]:
    """
    Get team summary stats for a season.

    Args:
        team: Team name or abbreviation (e.g., "Bills", "BUF")
        season: NFL season year

    Returns:
        {
            "ok": bool,
            "data": {
                "team": str,
                "season": int,
                "games": int,
                "wins": int,
                "losses": int,
                "points_for": <int>,
                "points_against": <int>,
                "offensive_epa": <float>,
                "offensive_epa_per_play": <float>,
                "defensive_epa_allowed": <float>,
                ...
            },
            "meta": {
                "team_abbr": "BUF",
                "source": "game_team_summary view"
            },
            "error": None
        }
    """
    # Resolve team name to abbreviation
    team_result = resolve_team(team)
    if not team_result["ok"]:
        return {
            "ok": False,
            "data": None,
            "error": team_result["error"],
            "meta": {}
        }

    team_abbr = team_result["team"]

    try:
        conn = get_db_connection()

        # Query game_team_summary to get aggregated stats
        result = conn.execute(
            """
            SELECT
                gts.team AS team,
                gts.season,
                COUNT(*) AS games,
                SUM(gts.offensive_yards) AS total_offensive_yards,
                SUM(gts.offensive_epa) AS total_offensive_epa,
                SUM(gts.defensive_epa_allowed) AS total_defensive_epa_allowed,
                SUM(gts.play_count) AS total_plays,
                AVG(gts.offensive_yards) AS avg_offensive_yards,
                AVG(gts.offensive_epa) AS avg_offensive_epa,
                AVG(gts.defensive_epa_allowed) AS avg_defensive_epa_allowed
            FROM game_team_summary gts
            JOIN games g ON g.game_id = gts.game_id
            WHERE gts.team = ?
              AND gts.season = ?
              AND g.game_type = 'REG'
            GROUP BY gts.team, gts.season
            """,
            [team_abbr, season],
        ).fetchall()

        if not result:
            conn.close()
            return {
                "ok": False,
                "data": None,
                "error": f"No data found for {team_abbr} in season {season}",
                "meta": {"team_abbr": team_abbr}
            }

        row = result[0]
        _, _, games, total_off_yards, total_off_epa, total_def_epa, total_plays, avg_off_yards, _, _ = row

        # Get wins/losses from games table
        games_result = conn.execute(
            """
            SELECT
                COUNT(*) AS total_games,
                SUM(CASE WHEN home_team = ? THEN 1 ELSE 0 END) AS home_games,
                SUM(CASE WHEN home_team = ? AND home_score > away_score THEN 1
                         WHEN away_team = ? AND away_score > home_score THEN 1
                         ELSE 0 END) AS wins,
                SUM(CASE WHEN home_team = ? AND home_score < away_score THEN 1
                         WHEN away_team = ? AND away_score < home_score THEN 1
                         ELSE 0 END) AS losses,
                SUM(CASE WHEN home_team = ? THEN home_score ELSE away_score END) AS points_for,
                SUM(CASE WHEN home_team = ? THEN away_score ELSE home_score END) AS points_against
            FROM games
            WHERE (home_team = ? OR away_team = ?)
              AND season = ?
              AND game_type = 'REG'
            """,
            [
                team_abbr,
                team_abbr,
                team_abbr,
                team_abbr,
                team_abbr,
                team_abbr,
                team_abbr,
                team_abbr,
                team_abbr,
                season,
            ],
        ).fetchall()

        conn.close()

        if games_result:
            total_games, home_games, wins, losses, points_for, points_against = games_result[0]
            wins = int(wins) if wins else 0
            losses = int(losses) if losses else 0
            points_for = int(points_for) if points_for else 0
            points_against = int(points_against) if points_against else 0
        else:
            total_games, home_games, wins, losses, points_for, points_against = 0, 0, 0, 0, 0, 0

        # Calculate EPA per play
        games = int(games) if games else 0
        plays = int(total_plays) if total_plays else 0
        if plays > 0:
            off_epa_per_play = float(total_off_epa) / plays if total_off_epa else 0.0
            def_epa_per_play = float(total_def_epa) / plays if total_def_epa else 0.0
        else:
            off_epa_per_play = 0.0
            def_epa_per_play = 0.0

        data = {
            "team": team_abbr,
            "season": int(season),
            "games": int(games),
            "wins": wins,
            "losses": losses,
            "points_for": points_for,
            "points_against": points_against,
            "offensive_epa": round(float(total_off_epa), 2) if total_off_epa else 0.0,
            "defensive_epa_allowed": round(float(total_def_epa), 2) if total_def_epa else 0.0,
            "defensive_epa_per_play_allowed": round(def_epa_per_play, 4),
            "offensive_epa_per_play": round(off_epa_per_play, 4),
            "avg_offensive_yards": round(float(avg_off_yards), 1) if avg_off_yards else 0.0,
            "play_count": plays,
        }

        return {
            "ok": True,
            "data": data,
            "error": None,
            "meta": {
                "team_abbr": team_abbr,
                "source": "game_team_summary view + games table"
            }
        }

    except Exception as e:
        return {
            "ok": False,
            "data": None,
            "error": str(e),
            "meta": {"team_abbr": team_abbr}
        }


def get_player_summary(player_name: str, season: int) -> Dict[str, Any]:
    """
    Get player summary stats for a season.

    Args:
        player_name: Player full name (e.g., "Josh Allen")
        season: NFL season year

    Returns:
        {
            "ok": bool,
            "data": {
                "player_id": str,
                "name": str,
                "position": str,
                "team": str,
                "games": int,
                "passing_yards": <int>,
                "passing_tds": <int>,
                "interceptions": <int>,
                "completion_pct": <float>,
                "rushing_yards": <int>,
                "rushing_tds": <int>,
                "receptions": <int>,
                "receiving_yards": <int>,
                "receiving_tds": <int>,
                ...
            },
            "meta": {
                "player_id": str,
                "source": "weekly" or "pbp_derived"
            },
            "error": None
        }
    """
    # Resolve player name
    player_result = resolve_player(player_name, season)
    if not player_result["ok"]:
        return {
            "ok": False,
            "data": None,
            "error": player_result["error"],
            "meta": {}
        }

    player_id = player_result["player_id"]
    player_name_canonical = player_result["name"]
    position = player_result["position"]
    team = player_result["team"]

    # Get stats from player_season_stats view
    stats_result = get_player_stats(player_id, season)

    if not stats_result["ok"]:
        return {
            "ok": False,
            "data": None,
            "error": stats_result["error"],
            "meta": {"player_id": player_id}
        }

    if not stats_result["stats"]:
        return {
            "ok": False,
            "data": None,
            "error": f"No stats found for {player_name_canonical} in season {season}",
            "meta": {"player_id": player_id}
        }

    stats = stats_result["stats"]
    source = stats_result["source"] or "unknown"

    # Extract key stats
    data = {
        "player_id": player_id,
        "name": player_name_canonical,
        "position": position,
        "team": team,
        "games": int(stats.get("games", 0)),
        "passing_attempts": int(stats.get("passing_attempts", 0)),
        "completions": int(stats.get("completions", 0)),
        "passing_yards": int(stats.get("passing_yards", 0)),
        "passing_tds": int(stats.get("passing_tds", 0)),
        "interceptions": int(stats.get("interceptions", 0)),
        "carries": int(stats.get("carries", 0)),
        "rushing_yards": int(stats.get("rushing_yards", 0)),
        "rushing_tds": int(stats.get("rushing_tds", 0)),
        "targets": int(stats.get("targets", 0)),
        "receptions": int(stats.get("receptions", 0)),
        "receiving_yards": int(stats.get("receiving_yards", 0)),
        "receiving_tds": int(stats.get("receiving_tds", 0)),
    }

    # Calculate completion percentage for QBs
    if data["passing_attempts"] > 0:
        data["completion_pct"] = round(data["completions"] / data["passing_attempts"], 3)

    # Mark 2025 as pbp_derived
    meta = {
        "player_id": player_id,
        "source": source
    }
    if season == 2025:
        meta["source"] = "pbp_derived"
        meta["2025_note"] = "Derived from play-by-play data"

    return {
        "ok": True,
        "data": data,
        "error": None,
        "meta": meta
    }


def compare_players(
    player_names: List[str],
    season: int,
    metrics: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Compare multiple players side-by-side.

    Args:
        player_names: List of player names
        season: NFL season year
        metrics: Optional list of metric names to include (if None, include all)

    Returns:
        {
            "ok": bool,
            "data": [
                {
                    "player_id": str,
                    "name": str,
                    "position": str,
                    "team": str,
                    "metric1": value,
                    "metric2": value,
                    ...
                },
                ...
            ],
            "meta": {
                "season": int,
                "players_compared": int,
                "metrics_included": [list of metric names]
            },
            "error": None
        }
    """
    if not player_names:
        return {
            "ok": False,
            "data": None,
            "error": "player_names cannot be empty",
            "meta": {}
        }

    comparisons = []
    for player_name in player_names:
        result = get_player_summary(player_name, season)
        if result["ok"] and result["data"]:
            comparisons.append(result["data"])
        else:
            # Include error indicator
            comparisons.append({
                "name": player_name,
                "error": result.get("error", "Unknown error")
            })

    if not comparisons:
        return {
            "ok": False,
            "data": None,
            "error": "Could not resolve any of the provided player names",
            "meta": {}
        }

    # Filter to requested metrics if specified
    if metrics:
        filtered = []
        for comp in comparisons:
            if "error" in comp:
                filtered.append(comp)
            else:
                filtered_comp = {
                    "player_id": comp["player_id"],
                    "name": comp["name"],
                    "position": comp["position"],
                    "team": comp["team"]
                }
                for metric in metrics:
                    if metric in comp:
                        filtered_comp[metric] = comp[metric]
                filtered.append(filtered_comp)
        comparisons = filtered

    meta = {
        "season": season,
        "players_compared": len([c for c in comparisons if "error" not in c]),
        "metrics_included": metrics if metrics else list(comparisons[0].keys()) if comparisons and "error" not in comparisons[0] else []
    }

    return {
        "ok": True,
        "data": comparisons,
        "error": None,
        "meta": meta
    }


def get_team_epa_trend(
    team: str,
    season: int,
    start_week: int,
    end_week: int
) -> Dict[str, Any]:
    """
    Get team EPA trend over a range of weeks.

    Args:
        team: Team name or abbreviation
        season: NFL season year
        start_week: Starting week (1-based)
        end_week: Ending week (1-based, inclusive)

    Returns:
        {
            "ok": bool,
            "data": [
                {
                    "week": int,
                    "offensive_epa": <float>,
                    "defensive_epa": <float>,
                    "net_epa": <float>,
                    "play_count": int
                },
                ...
            ],
            "meta": {
                "team_abbr": str,
                "season": int,
                "weeks_covered": int,
                "source": "team_week_epa view"
            },
            "error": None
        }
    """
    # Resolve team name
    team_result = resolve_team(team)
    if not team_result["ok"]:
        return {
            "ok": False,
            "data": None,
            "error": team_result["error"],
            "meta": {}
        }

    team_abbr = team_result["team"]

    try:
        conn = get_db_connection()

        result = conn.execute(
            """
            SELECT
                week,
                offensive_epa,
                defensive_epa_allowed,
                net_epa,
                play_count
            FROM team_week_epa
            WHERE team = ?
              AND season = ?
              AND week >= ?
              AND week <= ?
            ORDER BY week
            """,
            [team_abbr, season, start_week, end_week],
        ).fetchall()

        conn.close()

        if not result:
            return {
                "ok": False,
                "data": None,
                "error": f"No data found for {team_abbr} weeks {start_week}-{end_week} in season {season}",
                "meta": {"team_abbr": team_abbr, "season": season}
            }

        weeks_data = []
        for row in result:
            week, off_epa, def_epa_allowed, net_epa, play_count = row
            weeks_data.append({
                "week": int(week),
                "offensive_epa": round(float(off_epa), 2) if off_epa is not None else 0.0,
                "defensive_epa_allowed": round(float(def_epa_allowed), 2) if def_epa_allowed is not None else 0.0,
                "net_epa": round(float(net_epa), 2) if net_epa is not None else 0.0,
                "play_count": int(play_count) if play_count else 0
            })

        meta = {
            "team_abbr": team_abbr,
            "season": season,
            "weeks_covered": len(weeks_data),
            "source": "team_week_epa view"
        }

        return {
            "ok": True,
            "data": weeks_data,
            "error": None,
            "meta": meta
        }

    except Exception as e:
        return {
            "ok": False,
            "data": None,
            "error": str(e),
            "meta": {"team_abbr": team_abbr, "season": season}
        }


# ============================================================================
# Phase 4A: Fantasy Research Tools
# ============================================================================

def _calculate_fantasy_points(
    pass_yds: int,
    pass_td: int,
    interceptions: int,
    rush_yds: int,
    rush_td: int,
    rec_yds: int,
    rec_td: int,
    receptions: int,
    scoring: str = "ppr"
) -> float:
    """
    Calculate fantasy points based on scoring format.

    Args:
        scoring: "standard", "half_ppr", or "ppr"

    Returns:
        Total fantasy points (float)
    """
    # Standard scoring
    points = (
        pass_yds * 0.04
        + pass_td * 4
        - interceptions * 2
        + rush_yds * 0.1
        + rush_td * 6
        + rec_yds * 0.1
        + rec_td * 6
    )

    # Add reception scoring
    if scoring == "ppr":
        points += receptions * 1.0
    elif scoring == "half_ppr":
        points += receptions * 0.5

    return round(points, 2)


def get_fantasy_player_summary(
    player_name: str,
    season: int,
    scoring: str = "ppr"
) -> Dict[str, Any]:
    """
    Get player fantasy summary for a season.

    Args:
        player_name: Player full name (e.g., "Josh Allen")
        season: NFL season year
        scoring: "standard", "half_ppr", or "ppr" (default: "ppr")

    Returns:
        {
            "ok": bool,
            "data": {
                "player_id": str,
                "name": str,
                "position": str,
                "team": str,
                "games": int,
                "fantasy_points": float,
                "fantasy_points_per_game": float,
                "passing_yards": int,
                "passing_tds": int,
                "interceptions": int,
                "rushing_yards": int,
                "rushing_tds": int,
                "targets": int,
                "receptions": int,
                "receiving_yards": int,
                "receiving_tds": int,
                "carries": int,
                "scoring": str
            },
            "meta": {
                "player_id": str,
                "source": "weekly" or "pbp_derived",
                "scoring_format": str
            },
            "error": None
        }
    """
    # Validate scoring format
    if scoring not in ("standard", "half_ppr", "ppr"):
        return {
            "ok": False,
            "data": None,
            "error": f"Invalid scoring format: {scoring}. Use 'standard', 'half_ppr', or 'ppr'.",
            "meta": {}
        }

    # Resolve player
    player_result = resolve_player(player_name, season)
    if not player_result["ok"]:
        return {
            "ok": False,
            "data": None,
            "error": player_result["error"],
            "meta": {}
        }

    player_id = player_result["player_id"]
    player_name_canonical = player_result["name"]
    position = player_result["position"]
    team = player_result["team"]

    # Get stats
    stats_result = get_player_stats(player_id, season)
    if not stats_result["ok"]:
        return {
            "ok": False,
            "data": None,
            "error": stats_result["error"],
            "meta": {"player_id": player_id}
        }

    if not stats_result["stats"]:
        return {
            "ok": False,
            "data": None,
            "error": f"No stats found for {player_name_canonical} in season {season}",
            "meta": {"player_id": player_id}
        }

    stats = stats_result["stats"]
    source = stats_result["source"] or "unknown"

    # Extract stats
    games = int(stats.get("games", 0))
    pass_yds = int(stats.get("passing_yards", 0))
    pass_td = int(stats.get("passing_tds", 0))
    int_count = int(stats.get("interceptions", 0))
    rush_yds = int(stats.get("rushing_yards", 0))
    rush_td = int(stats.get("rushing_tds", 0))
    rec_yds = int(stats.get("receiving_yards", 0))
    rec_td = int(stats.get("receiving_tds", 0))
    receptions = int(stats.get("receptions", 0))
    carries = int(stats.get("carries", 0))
    targets = int(stats.get("targets", 0))

    # Calculate fantasy points
    fantasy_points = _calculate_fantasy_points(
        pass_yds, pass_td, int_count,
        rush_yds, rush_td,
        rec_yds, rec_td,
        receptions,
        scoring=scoring
    )

    fantasy_ppg = round(fantasy_points / games, 2) if games > 0 else 0.0

    data = {
        "player_id": player_id,
        "name": player_name_canonical,
        "position": position,
        "team": team,
        "season": season,
        "games": games,
        "fantasy_points": fantasy_points,
        "fantasy_points_per_game": fantasy_ppg,
        "passing_yards": pass_yds,
        "passing_tds": pass_td,
        "interceptions": int_count,
        "rushing_yards": rush_yds,
        "rushing_tds": rush_td,
        "targets": targets,
        "receptions": receptions,
        "receiving_yards": rec_yds,
        "receiving_tds": rec_td,
        "carries": carries,
        "scoring": scoring,
    }

    meta = {
        "player_id": player_id,
        "source": source,
        "scoring_format": scoring
    }
    if season == 2025:
        meta["source"] = "pbp_derived"
        meta["2025_note"] = "Derived from play-by-play data"

    return {
        "ok": True,
        "data": data,
        "error": None,
        "meta": meta
    }


def compare_fantasy_players(
    player_names: List[str],
    season: int,
    scoring: str = "ppr"
) -> Dict[str, Any]:
    """
    Compare multiple players' fantasy stats side-by-side.

    Args:
        player_names: List of player names
        season: NFL season year
        scoring: "standard", "half_ppr", or "ppr" (default: "ppr")

    Returns:
        {
            "ok": bool,
            "data": [
                {
                    "player_id": str,
                    "name": str,
                    "position": str,
                    "team": str,
                    "games": int,
                    "fantasy_points": float,
                    "fantasy_points_per_game": float,
                    "targets": int,
                    "receptions": int,
                    "receiving_yards": int,
                    "passing_yards": int,
                    "rushing_yards": int,
                    "scoring": str
                },
                ...
            ],
            "meta": {
                "season": int,
                "players_compared": int,
                "scoring_format": str
            },
            "error": None
        }
    """
    if not player_names:
        return {
            "ok": False,
            "data": None,
            "error": "player_names cannot be empty",
            "meta": {}
        }

    if scoring not in ("standard", "half_ppr", "ppr"):
        return {
            "ok": False,
            "data": None,
            "error": f"Invalid scoring format: {scoring}",
            "meta": {}
        }

    comparisons = []
    for player_name in player_names:
        result = get_fantasy_player_summary(player_name, season, scoring=scoring)
        if result["ok"] and result["data"]:
            comparisons.append(result["data"])
        else:
            comparisons.append({
                "name": player_name,
                "error": result.get("error", "Unknown error")
            })

    if not comparisons or all("error" in c for c in comparisons):
        return {
            "ok": False,
            "data": None,
            "error": "Could not resolve any of the provided player names",
            "meta": {}
        }

    meta = {
        "season": season,
        "players_compared": len([c for c in comparisons if "error" not in c]),
        "scoring_format": scoring
    }

    return {
        "ok": True,
        "data": comparisons,
        "error": None,
        "meta": meta
    }


def get_player_weekly_usage(
    player_name: str,
    season: int
) -> Dict[str, Any]:
    """
    Get player's weekly usage stats for a season.

    Args:
        player_name: Player full name
        season: NFL season year

    Returns:
        {
            "ok": bool,
            "data": [
                {
                    "week": int,
                    "opponent": str,
                    "carries": int,
                    "targets": int,
                    "receptions": int,
                    "rushing_yards": int,
                    "receiving_yards": int,
                    "passing_yards": int,
                    "tds": int,
                    "fantasy_points": float (PPR)
                },
                ...
            ],
            "meta": {
                "player_id": str,
                "name": str,
                "position": str,
                "source": "weekly" or "pbp_derived",
                "weeks_with_data": int
            },
            "error": None
        }
    """
    # Resolve player
    player_result = resolve_player(player_name, season)
    if not player_result["ok"]:
        return {
            "ok": False,
            "data": None,
            "error": player_result["error"],
            "meta": {}
        }

    player_id = player_result["player_id"]
    player_name_canonical = player_result["name"]
    position = player_result["position"]

    try:
        conn = get_db_connection()

        if season == 2025:
            result = conn.execute(
                """
                WITH player_events AS (
                    SELECT
                        week,
                        CASE
                            WHEN posteam = home_team THEN away_team
                            WHEN posteam = away_team THEN home_team
                            ELSE NULL
                        END AS opponent,
                        COALESCE(pass_attempt, 0) AS passing_attempts,
                        COALESCE(complete_pass, 0) AS completions,
                        COALESCE(passing_yards, 0) AS passing_yards,
                        COALESCE(pass_touchdown, 0) AS passing_tds,
                        COALESCE(interception, 0) AS interceptions,
                        0 AS carries,
                        0 AS targets,
                        0 AS receptions,
                        0 AS rushing_yards,
                        0 AS rushing_tds,
                        0 AS receiving_yards,
                        0 AS receiving_tds
                    FROM plays
                    WHERE season = ? AND passer_player_id = ?
                    UNION ALL
                    SELECT
                        week,
                        CASE
                            WHEN posteam = home_team THEN away_team
                            WHEN posteam = away_team THEN home_team
                            ELSE NULL
                        END AS opponent,
                        0 AS passing_attempts,
                        0 AS completions,
                        0 AS passing_yards,
                        0 AS passing_tds,
                        0 AS interceptions,
                        COALESCE(rush_attempt, 0) AS carries,
                        0 AS targets,
                        0 AS receptions,
                        COALESCE(rushing_yards, 0) AS rushing_yards,
                        COALESCE(rush_touchdown, 0) AS rushing_tds,
                        0 AS receiving_yards,
                        0 AS receiving_tds
                    FROM plays
                    WHERE season = ? AND rusher_player_id = ?
                    UNION ALL
                    SELECT
                        week,
                        CASE
                            WHEN posteam = home_team THEN away_team
                            WHEN posteam = away_team THEN home_team
                            ELSE NULL
                        END AS opponent,
                        0 AS passing_attempts,
                        0 AS completions,
                        0 AS passing_yards,
                        0 AS passing_tds,
                        0 AS interceptions,
                        0 AS carries,
                        1 AS targets,
                        COALESCE(complete_pass, 0) AS receptions,
                        0 AS rushing_yards,
                        0 AS rushing_tds,
                        COALESCE(receiving_yards, 0) AS receiving_yards,
                        COALESCE(pass_touchdown, 0) AS receiving_tds
                    FROM plays
                    WHERE season = ? AND receiver_player_id = ?
                )
                SELECT
                    week,
                    MAX(opponent) AS opponent,
                    SUM(carries) AS carries,
                    SUM(targets) AS targets,
                    SUM(receptions) AS receptions,
                    SUM(rushing_yards) AS rushing_yards,
                    SUM(receiving_yards) AS receiving_yards,
                    SUM(passing_yards) AS passing_yards,
                    SUM(passing_tds) AS passing_tds,
                    SUM(rushing_tds) AS rushing_tds,
                    SUM(receiving_tds) AS receiving_tds,
                    SUM(interceptions) AS interceptions
                FROM player_events
                GROUP BY week
                ORDER BY week
                """,
                [season, player_id, season, player_id, season, player_id],
            ).fetchall()
            source = "pbp_derived"
        else:
            result = conn.execute(
                """
                SELECT
                    week,
                    opponent_team AS opponent,
                    carries,
                    targets,
                    receptions,
                    rushing_yards,
                    receiving_yards,
                    passing_yards,
                    passing_tds,
                    rushing_tds,
                    receiving_tds,
                    interceptions
                FROM weekly
                WHERE player_id = ?
                  AND season = ?
                ORDER BY week
                """,
                [player_id, season],
            ).fetchall()
            source = "weekly"

        conn.close()

        if not result:
            return {
                "ok": False,
                "data": None,
                "error": f"No weekly data found for {player_name_canonical} in season {season}",
                "meta": {"player_id": player_id, "name": player_name_canonical, "position": position}
            }

        weeks_data = []
        for row in result:
            (week, opponent, carries, targets, receptions,
             rush_yds, rec_yds, pass_yds,
             pass_td, rush_td, rec_td, interceptions) = row

            # Calculate PPR fantasy points for this week
            week_points = _calculate_fantasy_points(
                int(pass_yds or 0), int(pass_td or 0), int(interceptions or 0),
                int(rush_yds or 0), int(rush_td or 0),
                int(rec_yds or 0), int(rec_td or 0),
                int(receptions or 0),
                scoring="ppr"
            )

            weeks_data.append({
                "week": int(week),
                "opponent": opponent or "N/A",
                "carries": int(carries or 0),
                "targets": int(targets or 0),
                "receptions": int(receptions or 0),
                "rushing_yards": int(rush_yds or 0),
                "receiving_yards": int(rec_yds or 0),
                "passing_yards": int(pass_yds or 0),
                "tds": int((pass_td or 0) + (rush_td or 0) + (rec_td or 0)),
                "fantasy_points_ppr": week_points,
            })

        meta = {
            "player_id": player_id,
            "name": player_name_canonical,
            "position": position,
            "source": source,
            "weeks_with_data": len(weeks_data)
        }
        if season == 2025:
            meta["2025_note"] = "Derived from play-by-play data"

        return {
            "ok": True,
            "data": weeks_data,
            "error": None,
            "meta": meta
        }

    except Exception as e:
        return {
            "ok": False,
            "data": None,
            "error": str(e),
            "meta": {"player_id": player_id}
        }


# ============================================================================
# Phase 4B: Draft Research Tools
# ============================================================================

FANTASY_POSITIONS = {"RB", "WR", "TE", "QB", "K"}
MINIMUM_ADVANCED_SAMPLE = 5


def _normalize_position(position: Optional[str], allow_none: bool = False) -> Optional[str]:
    """Normalize and validate a fantasy position filter."""
    if position is None and allow_none:
        return None
    if not position or not str(position).strip():
        raise ValueError("position is required")

    normalized = str(position).strip().upper()
    if normalized == "ALL" and allow_none:
        return None
    if normalized not in FANTASY_POSITIONS:
        raise ValueError(f"Unsupported position '{position}'. Use one of: QB, RB, WR, TE, K.")
    return normalized


def _opportunities_for_position(position: str, carries: int, targets: int) -> int:
    """Return the simple opportunity definition used by draft research tools."""
    if position in ("WR", "TE"):
        return targets
    return carries + targets


def _pct_change(old_value: float, new_value: float) -> Optional[float]:
    """Calculate percent change; return None when the old value is zero."""
    if old_value == 0:
        return None
    return round(((new_value - old_value) / old_value) * 100, 1)


def _rate_or_none(value: Optional[float], sample_size: int, digits: int = 3) -> Optional[float]:
    """Return a rounded rate only when the sample is large enough."""
    if sample_size < MINIMUM_ADVANCED_SAMPLE or value is None:
        return None
    return round(float(value), digits)


def _sample_note(sample_size: int, label: str) -> Optional[str]:
    """Return a small-sample note for rate fields."""
    if sample_size < MINIMUM_ADVANCED_SAMPLE:
        return f"Fewer than {MINIMUM_ADVANCED_SAMPLE} {label}"
    return None


def _weekly_research_rows(season: int, position: Optional[str] = None) -> Dict[str, Any]:
    """Return weekly usage rows from weekly stats or 2025 play-by-play-derived data."""
    if season < 2020 or season > 2025:
        return {
            "ok": False,
            "data": None,
            "error": f"Season {season} out of supported range (2020-2025)",
            "meta": {},
        }

    try:
        conn = get_db_connection()
        if season == 2025:
            position_filter = "AND roster.position = ?" if position else ""
            params = [season, season, season, season]
            if position:
                params.append(position)
            rows = conn.execute(
                f"""
                WITH roster AS (
                    SELECT
                        gsis_id AS player_id,
                        full_name AS player_name,
                        position,
                        team,
                        ROW_NUMBER() OVER (
                            PARTITION BY gsis_id
                            ORDER BY week DESC, team
                        ) AS row_num
                    FROM rosters
                    WHERE season = ?
                      AND gsis_id IS NOT NULL
                      AND full_name IS NOT NULL
                ),
                events AS (
                    SELECT
                        season,
                        week,
                        passer_player_id AS player_id,
                        posteam AS team,
                        0 AS carries,
                        0 AS targets,
                        0 AS receptions,
                        0 AS rushing_yards,
                        0 AS rushing_tds,
                        0 AS receiving_yards,
                        0 AS receiving_tds,
                        COALESCE(passing_yards, 0) AS passing_yards,
                        COALESCE(pass_touchdown, 0) AS passing_tds,
                        COALESCE(interception, 0) AS interceptions
                    FROM plays
                    WHERE season = ? AND passer_player_id IS NOT NULL
                    UNION ALL
                    SELECT
                        season,
                        week,
                        rusher_player_id AS player_id,
                        posteam AS team,
                        COALESCE(rush_attempt, 0) AS carries,
                        0 AS targets,
                        0 AS receptions,
                        COALESCE(rushing_yards, 0) AS rushing_yards,
                        COALESCE(rush_touchdown, 0) AS rushing_tds,
                        0 AS receiving_yards,
                        0 AS receiving_tds,
                        0 AS passing_yards,
                        0 AS passing_tds,
                        0 AS interceptions
                    FROM plays
                    WHERE season = ? AND rusher_player_id IS NOT NULL
                    UNION ALL
                    SELECT
                        season,
                        week,
                        receiver_player_id AS player_id,
                        posteam AS team,
                        0 AS carries,
                        1 AS targets,
                        COALESCE(complete_pass, 0) AS receptions,
                        0 AS rushing_yards,
                        0 AS rushing_tds,
                        COALESCE(receiving_yards, 0) AS receiving_yards,
                        COALESCE(pass_touchdown, 0) AS receiving_tds,
                        0 AS passing_yards,
                        0 AS passing_tds,
                        0 AS interceptions
                    FROM plays
                    WHERE season = ? AND receiver_player_id IS NOT NULL
                )
                SELECT
                    events.player_id,
                    COALESCE(roster.player_name, events.player_id) AS player_name,
                    roster.position,
                    COALESCE(events.team, roster.team) AS team,
                    events.week,
                    SUM(events.carries) AS carries,
                    SUM(events.targets) AS targets,
                    SUM(events.receptions) AS receptions,
                    SUM(events.rushing_yards) AS rushing_yards,
                    SUM(events.rushing_tds) AS rushing_tds,
                    SUM(events.receiving_yards) AS receiving_yards,
                    SUM(events.receiving_tds) AS receiving_tds,
                    SUM(events.passing_yards) AS passing_yards,
                    SUM(events.passing_tds) AS passing_tds,
                    SUM(events.interceptions) AS interceptions
                FROM events
                LEFT JOIN roster
                  ON events.player_id = roster.player_id
                 AND roster.row_num = 1
                WHERE roster.position IS NOT NULL
                {position_filter}
                GROUP BY
                    events.player_id,
                    COALESCE(roster.player_name, events.player_id),
                    roster.position,
                    COALESCE(events.team, roster.team),
                    events.week
                ORDER BY events.week, player_name
                """,
                params,
            ).fetchall()
            source = "pbp_derived"
        else:
            position_filter = "AND position = ?" if position else "AND position != 'QB'"
            params = [season]
            if position:
                params.append(position)
            rows = conn.execute(
                f"""
                SELECT
                    player_id,
                    player_display_name AS player_name,
                    position,
                    recent_team AS team,
                    week,
                    carries,
                    targets,
                    receptions,
                    rushing_yards,
                    rushing_tds,
                    receiving_yards,
                    receiving_tds,
                    passing_yards,
                    passing_tds,
                    interceptions
                FROM weekly
                WHERE season = ?
                  {position_filter}
                ORDER BY week, player_display_name
                """,
                params,
            ).fetchall()
            source = "weekly"
        conn.close()
    except Exception as exc:
        return {"ok": False, "data": None, "error": str(exc), "meta": {}}

    data = []
    for row in rows:
        (
            player_id,
            player_name,
            row_position,
            team,
            week,
            carries,
            targets,
            receptions,
            rushing_yards,
            rushing_tds,
            receiving_yards,
            receiving_tds,
            passing_yards,
            passing_tds,
            interceptions,
        ) = row
        row_position = str(row_position) if row_position else None
        carries = int(carries or 0)
        targets = int(targets or 0)
        receptions = int(receptions or 0)
        rushing_yards = int(rushing_yards or 0)
        rushing_tds = int(rushing_tds or 0)
        receiving_yards = int(receiving_yards or 0)
        receiving_tds = int(receiving_tds or 0)
        passing_yards = int(passing_yards or 0)
        passing_tds = int(passing_tds or 0)
        interceptions = int(interceptions or 0)
        data.append({
            "player_id": str(player_id),
            "name": str(player_name),
            "position": row_position,
            "team": str(team) if team else None,
            "week": int(week),
            "carries": carries,
            "targets": targets,
            "receptions": receptions,
            "rushing_yards": rushing_yards,
            "rushing_tds": rushing_tds,
            "receiving_yards": receiving_yards,
            "receiving_tds": receiving_tds,
            "passing_yards": passing_yards,
            "passing_tds": passing_tds,
            "interceptions": interceptions,
            "opportunities": _opportunities_for_position(row_position or "", carries, targets),
            "ppr_points": _calculate_fantasy_points(
                passing_yards,
                passing_tds,
                interceptions,
                rushing_yards,
                rushing_tds,
                receiving_yards,
                receiving_tds,
                receptions,
                scoring="ppr",
            ),
        })

    meta = {"source": source, "season": season, "position": position}
    if season == 2025:
        meta["2025_note"] = "Derived from play-by-play data"
    return {"ok": True, "data": data, "error": None, "meta": meta}


def _aggregate_player_period(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate weekly rows into a period summary."""
    games = len(rows)
    opportunities = sum(row["opportunities"] for row in rows)
    ppr_points = round(sum(row["ppr_points"] for row in rows), 2)
    targets = sum(row["targets"] for row in rows)
    carries = sum(row["carries"] for row in rows)
    receptions = sum(row["receptions"] for row in rows)
    receiving_yards = sum(row["receiving_yards"] for row in rows)
    rushing_yards = sum(row["rushing_yards"] for row in rows)
    touchdowns = sum(row["rushing_tds"] + row["receiving_tds"] + row["passing_tds"] for row in rows)
    return {
        "games": games,
        "opportunities": opportunities,
        "opportunities_per_game": round(opportunities / games, 2) if games else 0.0,
        "ppr_points": ppr_points,
        "ppr_points_per_game": round(ppr_points / games, 2) if games else 0.0,
        "targets": targets,
        "carries": carries,
        "receptions": receptions,
        "receiving_yards": receiving_yards,
        "rushing_yards": rushing_yards,
        "touchdowns": touchdowns,
    }


def _period_change_player_rows(
    rows: List[Dict[str, Any]],
    early_start: int,
    early_end: int,
    late_start: int,
    late_end: int,
    min_early_opportunities: int = 10,
    min_late_opportunities: int = 15,
) -> List[Dict[str, Any]]:
    """Build before/after player rows that pass draft-research noise thresholds."""
    grouped: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        player_id = row["player_id"]
        if player_id not in grouped:
            grouped[player_id] = {
                "player_id": player_id,
                "name": row["name"],
                "team": row["team"],
                "position": row["position"],
                "early_rows": [],
                "late_rows": [],
            }
        if early_start <= row["week"] <= early_end:
            grouped[player_id]["early_rows"].append(row)
        elif late_start <= row["week"] <= late_end:
            grouped[player_id]["late_rows"].append(row)

    output = []
    for player in grouped.values():
        early = _aggregate_player_period(player["early_rows"])
        late = _aggregate_player_period(player["late_rows"])
        if early["opportunities"] < min_early_opportunities or late["opportunities"] < min_late_opportunities:
            continue

        opportunity_delta = round(late["opportunities_per_game"] - early["opportunities_per_game"], 2)
        ppr_delta = round(late["ppr_points_per_game"] - early["ppr_points_per_game"], 2)
        opportunity_pct = _pct_change(early["opportunities_per_game"], late["opportunities_per_game"])
        ppr_pct = _pct_change(early["ppr_points_per_game"], late["ppr_points_per_game"])
        opportunity_pct_value = opportunity_pct if opportunity_pct is not None else 0.0
        ppr_pct_value = ppr_pct if ppr_pct is not None else 0.0

        if not (
            opportunity_delta >= 3.0
            and ppr_delta >= 3.0
            and (opportunity_pct_value >= 25.0 or ppr_pct_value >= 25.0)
        ):
            continue

        output.append({
            "player_id": player["player_id"],
            "name": player["name"],
            "team": player["team"],
            "position": player["position"],
            "early": {
                "weeks": f"{early_start}-{early_end}",
                **early,
            },
            "late": {
                "weeks": f"{late_start}-{late_end}",
                **late,
            },
            "change": {
                "opportunities_per_game_delta": opportunity_delta,
                "opportunities_per_game_pct": opportunity_pct,
                "ppr_points_per_game_delta": ppr_delta,
                "ppr_points_per_game_pct": ppr_pct,
            },
        })

    return output


def find_usage_risers(
    position: str,
    season: int,
    start_week: int,
    end_week: int
) -> Dict[str, Any]:
    """
    Find players whose opportunity and PPR usage rose within a week range.

    The week range is split in half. For example, weeks 1-17 compares
    weeks 1-8 against weeks 9-17.
    """
    try:
        position_code = _normalize_position(position)
    except ValueError as exc:
        return {"ok": False, "data": None, "error": str(exc), "meta": {}}

    if start_week < 1 or end_week > 22 or start_week >= end_week:
        return {
            "ok": False,
            "data": None,
            "error": "Use a valid week range where 1 <= start_week < end_week <= 22",
            "meta": {},
        }

    midpoint = start_week + ((end_week - start_week + 1) // 2) - 1
    weekly = _weekly_research_rows(season, position_code)
    if not weekly["ok"]:
        return weekly

    data = _period_change_player_rows(
        weekly["data"],
        start_week,
        midpoint,
        midpoint + 1,
        end_week,
    )
    data.sort(key=lambda row: row["change"]["opportunities_per_game_delta"], reverse=True)

    return {
        "ok": True,
        "data": data,
        "error": None,
        "meta": {
            **weekly["meta"],
            "position": position_code,
            "early_weeks": f"{start_week}-{midpoint}",
            "late_weeks": f"{midpoint + 1}-{end_week}",
            "sort": "opportunities_per_game_delta_desc",
            "minimums": {"early_opportunities": 10, "late_opportunities": 15},
            "thresholds": {
                "opportunities_per_game_delta": 3.0,
                "ppr_points_per_game_delta": 3.0,
                "relative_increase_pct": 25.0,
            },
        },
    }


def find_target_opportunity_players(
    season: int,
    min_targets: int,
    position: Optional[str] = None
) -> Dict[str, Any]:
    """Find players with high target volume and team target share."""
    try:
        position_code = _normalize_position(position, allow_none=True)
    except ValueError as exc:
        return {"ok": False, "data": None, "error": str(exc), "meta": {}}

    if min_targets < 1:
        return {"ok": False, "data": None, "error": "min_targets must be at least 1", "meta": {}}

    weekly = _weekly_research_rows(season, None)
    if not weekly["ok"]:
        return weekly

    grouped: Dict[str, Dict[str, Any]] = {}
    team_targets: Dict[str, int] = {}
    for row in weekly["data"]:
        if row["position"] == "QB":
            continue
        team = row["team"] or "UNK"
        team_targets[team] = team_targets.get(team, 0) + row["targets"]
        if position_code and row["position"] != position_code:
            continue
        player_id = row["player_id"]
        if player_id not in grouped:
            grouped[player_id] = {
                "player_id": player_id,
                "name": row["name"],
                "team": team,
                "position": row["position"],
                "games": 0,
                "targets": 0,
                "receptions": 0,
                "receiving_yards": 0,
                "receiving_tds": 0,
                "ppr_points": 0.0,
            }
        grouped[player_id]["games"] += 1
        grouped[player_id]["targets"] += row["targets"]
        grouped[player_id]["receptions"] += row["receptions"]
        grouped[player_id]["receiving_yards"] += row["receiving_yards"]
        grouped[player_id]["receiving_tds"] += row["receiving_tds"]
        grouped[player_id]["ppr_points"] = round(grouped[player_id]["ppr_points"] + row["ppr_points"], 2)

    data = []
    for player in grouped.values():
        if player["targets"] < min_targets:
            continue
        team_total_targets = team_targets.get(player["team"], 0)
        target_share = round(player["targets"] / team_total_targets, 4) if team_total_targets else 0.0
        player["target_share"] = target_share
        player["targets_per_game"] = round(player["targets"] / player["games"], 2) if player["games"] else 0.0
        player["ppr_points_per_game"] = round(player["ppr_points"] / player["games"], 2) if player["games"] else 0.0
        data.append(player)

    data.sort(key=lambda row: (row["target_share"], row["targets"]), reverse=True)

    return {
        "ok": True,
        "data": data,
        "error": None,
        "meta": {
            **weekly["meta"],
            "position": position_code,
            "min_targets": min_targets,
            "sort": "target_share_desc",
        },
    }


def find_late_season_breakouts(position: str, season: int) -> Dict[str, Any]:
    """Find players with materially better usage and PPR scoring in weeks 9-17."""
    try:
        position_code = _normalize_position(position)
    except ValueError as exc:
        return {"ok": False, "data": None, "error": str(exc), "meta": {}}

    weekly = _weekly_research_rows(season, position_code)
    if not weekly["ok"]:
        return weekly

    data = _period_change_player_rows(weekly["data"], 1, 8, 9, 17)
    data.sort(key=lambda row: row["change"]["ppr_points_per_game_delta"], reverse=True)

    return {
        "ok": True,
        "data": data,
        "error": None,
        "meta": {
            **weekly["meta"],
            "position": position_code,
            "early_weeks": "1-8",
            "late_weeks": "9-17",
            "sort": "ppr_points_per_game_delta_desc",
            "minimums": {"early_opportunities": 10, "late_opportunities": 15},
            "thresholds": {
                "opportunities_per_game_delta": 3.0,
                "ppr_points_per_game_delta": 3.0,
                "relative_increase_pct": 25.0,
            },
        },
    }


# ============================================================================
# Phase 5: Player EPA & Advanced Analytics
# ============================================================================

def get_player_advanced_summary(player_name: str, season: int) -> Dict[str, Any]:
    """
    Get player EPA, success rate, CPOE, and position-relevant advanced metrics.
    """
    player_result = resolve_player(player_name, season)
    if not player_result["ok"]:
        return {"ok": False, "data": None, "error": player_result["error"], "meta": {}}

    player_id = player_result["player_id"]
    canonical_name = player_result["name"]
    position = player_result["position"]
    team = player_result["team"]

    try:
        conn = get_db_connection()
        pass_row = conn.execute(
            """
            SELECT
                COUNT(*) AS plays,
                AVG(epa) AS epa_per_play,
                AVG(qb_epa) AS qb_epa_per_play,
                AVG(success) AS success_rate,
                AVG(cpoe) AS cpoe,
                AVG(cp) AS cp
            FROM plays
            WHERE season = ?
              AND passer_player_id = ?
              AND play_type = 'pass'
              AND COALESCE(qb_spike, 0) = 0
            """,
            [season, player_id],
        ).fetchone()
        rush_row = conn.execute(
            """
            SELECT
                COUNT(*) AS attempts,
                AVG(epa) AS epa_per_attempt,
                AVG(success) AS success_rate,
                SUM(epa) AS total_epa
            FROM plays
            WHERE season = ?
              AND rusher_player_id = ?
              AND COALESCE(rush_attempt, 0) = 1
              AND COALESCE(qb_kneel, 0) = 0
            """,
            [season, player_id],
        ).fetchone()
        receiving_row = conn.execute(
            """
            SELECT
                COUNT(*) AS targets,
                AVG(epa) AS epa_per_target,
                AVG(success) AS success_rate,
                AVG(air_epa) AS air_epa_per_target,
                AVG(yac_epa) AS yac_epa_per_target,
                AVG(xyac_epa) AS xyac_epa_per_target,
                SUM(epa) AS total_epa
            FROM plays
            WHERE season = ?
              AND receiver_player_id = ?
            """,
            [season, player_id],
        ).fetchone()
        scramble_row = conn.execute(
            """
            SELECT
                COUNT(*) AS scrambles,
                AVG(epa) AS epa_per_play,
                AVG(success) AS success_rate,
                SUM(epa) AS total_epa
            FROM plays
            WHERE season = ?
              AND rusher_player_id = ?
              AND COALESCE(qb_scramble, 0) = 1
            """,
            [season, player_id],
        ).fetchone()
        conn.close()
    except Exception as exc:
        return {"ok": False, "data": None, "error": str(exc), "meta": {"player_id": player_id}}

    pass_count = int(pass_row[0] or 0)
    rush_count = int(rush_row[0] or 0)
    target_count = int(receiving_row[0] or 0)
    scramble_count = int(scramble_row[0] or 0)
    total_opportunities = rush_count + target_count
    total_epa = float(rush_row[3] or 0.0) + float(receiving_row[6] or 0.0)
    total_epa_per_opportunity = (
        round(total_epa / total_opportunities, 3)
        if total_opportunities >= MINIMUM_ADVANCED_SAMPLE
        else None
    )

    passing = {
        "pass_plays": pass_count,
        "passing_epa_per_play": _rate_or_none(pass_row[1], pass_count, 3),
        "qb_epa_per_play": _rate_or_none(pass_row[2], pass_count, 3),
        "pass_success_rate": _rate_or_none(pass_row[3], pass_count, 3),
        "cpoe": _rate_or_none(pass_row[4], pass_count, 2),
        "cp": _rate_or_none(pass_row[5], pass_count, 3),
    }
    note = _sample_note(pass_count, "pass plays")
    if note:
        passing["sample_note"] = note

    rushing = {
        "rush_attempts": rush_count,
        "rushing_epa_per_attempt": _rate_or_none(rush_row[1], rush_count, 3),
        "rush_success_rate": _rate_or_none(rush_row[2], rush_count, 3),
    }
    note = _sample_note(rush_count, "rush attempts")
    if note:
        rushing["sample_note"] = note

    receiving = {
        "targets": target_count,
        "receiving_epa_per_target": _rate_or_none(receiving_row[1], target_count, 3),
        "receiving_success_rate": _rate_or_none(receiving_row[2], target_count, 3),
        "air_epa_per_target": _rate_or_none(receiving_row[3], target_count, 3),
        "yac_epa_per_target": _rate_or_none(receiving_row[4], target_count, 3),
        "xyac_epa_per_target": _rate_or_none(receiving_row[5], target_count, 3),
    }
    note = _sample_note(target_count, "targets")
    if note:
        receiving["sample_note"] = note

    scrambles = {
        "scrambles": scramble_count,
        "scramble_epa_per_play": _rate_or_none(scramble_row[1], scramble_count, 3),
        "scramble_success_rate": _rate_or_none(scramble_row[2], scramble_count, 3),
    }
    note = _sample_note(scramble_count, "scrambles")
    if note:
        scrambles["sample_note"] = note

    data = {
        "player_id": player_id,
        "name": canonical_name,
        "position": position,
        "team": team,
        "season": season,
        "plays_analyzed": pass_count + rush_count + target_count,
        "total_opportunities": total_opportunities,
        "total_epa_per_opportunity": total_epa_per_opportunity,
        "passing": passing,
        "rushing": rushing,
        "receiving": receiving,
        "scrambles": scrambles,
    }

    if position == "QB":
        data["primary_metrics"] = {
            "epa_per_play": passing["qb_epa_per_play"] or passing["passing_epa_per_play"],
            "success_rate": passing["pass_success_rate"],
            "cpoe": passing["cpoe"],
        }
    elif position == "RB":
        data["primary_metrics"] = {
            "epa_per_play": total_epa_per_opportunity,
            "success_rate": _rate_or_none(
                (
                    (float(rush_row[2] or 0.0) * rush_count)
                    + (float(receiving_row[2] or 0.0) * target_count)
                ) / total_opportunities
                if total_opportunities
                else None,
                total_opportunities,
                3,
            ),
            "rushing_epa_per_attempt": rushing["rushing_epa_per_attempt"],
            "receiving_epa_per_target": receiving["receiving_epa_per_target"],
        }
    else:
        data["primary_metrics"] = {
            "epa_per_play": receiving["receiving_epa_per_target"],
            "success_rate": receiving["receiving_success_rate"],
            "air_epa_per_target": receiving["air_epa_per_target"],
            "yac_epa_per_target": receiving["yac_epa_per_target"],
        }

    meta = {
        "player_id": player_id,
        "source": "plays",
        "minimum_sample_for_rates": MINIMUM_ADVANCED_SAMPLE,
        "epa_source": "nflverse precomputed epa/qb_epa",
        "success_source": "nflverse success column",
        "cp_scale": "nflverse completion probability scale",
    }
    if season == 2025:
        meta["2025_note"] = "Derived from play-by-play data"

    return {"ok": True, "data": data, "error": None, "meta": meta}


def compare_player_advanced(
    player_names: List[str],
    season: int,
    metrics: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Compare multiple players by advanced EPA and success-rate metrics."""
    if not player_names:
        return {"ok": False, "data": None, "error": "player_names cannot be empty", "meta": {}}

    default_metrics = ["epa_per_play", "success_rate", "cpoe"]
    selected_metrics = metrics or default_metrics

    comparisons = []
    for player_name in player_names:
        result = get_player_advanced_summary(player_name, season)
        if not result["ok"]:
            comparisons.append({"name": player_name, "error": result.get("error", "Unknown error")})
            continue

        data = result["data"]
        primary = data.get("primary_metrics", {})
        row = {
            "player_id": data["player_id"],
            "name": data["name"],
            "position": data["position"],
            "team": data["team"],
            "season": data["season"],
            "plays_analyzed": data["plays_analyzed"],
            "total_opportunities": data["total_opportunities"],
        }
        for metric in selected_metrics:
            if metric in primary:
                row[metric] = primary.get(metric)
            elif metric in data:
                row[metric] = data.get(metric)
            elif metric in data.get("passing", {}):
                row[metric] = data["passing"].get(metric)
            elif metric in data.get("rushing", {}):
                row[metric] = data["rushing"].get(metric)
            elif metric in data.get("receiving", {}):
                row[metric] = data["receiving"].get(metric)
            elif metric in data.get("scrambles", {}):
                row[metric] = data["scrambles"].get(metric)
            else:
                row[metric] = None
        comparisons.append(row)

    if all("error" in row for row in comparisons):
        return {
            "ok": False,
            "data": None,
            "error": "Could not resolve any of the provided player names",
            "meta": {},
        }

    return {
        "ok": True,
        "data": comparisons,
        "error": None,
        "meta": {
            "season": season,
            "players_compared": len([row for row in comparisons if "error" not in row]),
            "metrics": selected_metrics,
            "source": "plays",
            "minimum_sample_for_rates": MINIMUM_ADVANCED_SAMPLE,
        },
    }


def get_team_schedule_context(team: str, season: int) -> Dict[str, Any]:
    """
    Get a team's full season schedule with results.

    Args:
        team: Team name or abbreviation (e.g., "Bills", "BUF")
        season: NFL season year

    Returns:
        {
            "ok": bool,
            "data": {
                "team": "BUF",
                "season": 2025,
                "bye_week": 9,
                "schedule": [
                    {
                        "week": 1,
                        "game_id": "...",
                        "opponent": "MIA",
                        "location": "home" | "away",
                        "game_date": "2025-09-07",
                        "result": "W" | "L" | null,
                        "team_score": 31 | null,
                        "opponent_score": 24 | null
                    },
                    ...
                ]
            },
            "meta": {...}
        }
    """
    # Resolve team
    team_result = resolve_team(team)
    if not team_result["ok"]:
        return {
            "ok": False,
            "data": None,
            "error": f"Could not resolve team: {team}",
            "meta": {}
        }

    team_abbr = team_result["team"]

    try:
        conn = get_db_connection()

        # Query games where team played
        query = """
        SELECT
            week,
            game_id,
            home_team,
            away_team,
            home_score,
            away_score,
            gameday
        FROM games
        WHERE season = ?
            AND (home_team = ? OR away_team = ?)
            AND game_type = 'REG'
        ORDER BY week ASC
        """

        games = conn.execute(query, [season, team_abbr, team_abbr]).fetchall()

        # Get all weeks in season (typically 1-17)
        all_weeks_query = """
        SELECT DISTINCT week
        FROM games
        WHERE season = ? AND game_type = 'REG'
        ORDER BY week
        """
        all_weeks = [row[0] for row in conn.execute(all_weeks_query, [season]).fetchall()]
        conn.close()

        # Find bye week by checking which weeks the team didn't play
        weeks_played = set(row[0] for row in games)
        bye_week = None
        for week in all_weeks:
            if week not in weeks_played:
                bye_week = week
                break

        # Build schedule with results
        schedule = []
        for row in games:
            week, game_id, home_team, away_team, home_score, away_score, gameday = row

            is_home = home_team == team_abbr
            opponent = away_team if is_home else home_team
            location = "home" if is_home else "away"
            team_score = home_score if is_home else away_score
            opp_score = away_score if is_home else home_score

            # Determine result
            result = None
            if team_score is not None and opp_score is not None:
                if team_score > opp_score:
                    result = "W"
                elif team_score < opp_score:
                    result = "L"
                else:
                    result = "T"

            schedule.append({
                "week": int(week),
                "game_id": game_id,
                "opponent": opponent,
                "location": location,
                "game_date": gameday,
                "result": result,
                "team_score": team_score,
                "opponent_score": opp_score,
            })

        # Add bye week as synthetic row if present
        if bye_week:
            # Insert at the correct position (week - 1 index)
            bye_row = {
                "week": int(bye_week),
                "bye": True,
                "opponent": None,
                "location": None,
                "game_date": None,
                "result": None,
                "team_score": None,
                "opponent_score": None,
            }
            # Find correct insertion point
            for i, game in enumerate(schedule):
                if game["week"] > bye_week:
                    schedule.insert(i, bye_row)
                    break
            else:
                schedule.append(bye_row)

        return {
            "ok": True,
            "data": {
                "team": team_abbr,
                "season": season,
                "bye_week": bye_week,
                "schedule": schedule,
            },
            "error": None,
            "meta": {
                "source": "games table",
                "schedule_count": len(schedule),
                "regular_season_only": True,
            }
        }

    except Exception as e:
        return {
            "ok": False,
            "data": None,
            "error": f"Error fetching schedule: {str(e)}",
            "meta": {}
        }


def get_bye_weeks(season: int, team: Optional[str] = None) -> Dict[str, Any]:
    """
    Get bye weeks for a season.

    Args:
        season: NFL season year
        team: Optional team abbreviation. If provided, returns only that team's bye week.

    Returns:
        {
            "ok": bool,
            "data": {
                "season": 2025,
                "bye_weeks": {
                    "8": ["BUF", "NE", "NYJ"],
                    "9": ["KC", "LAC", "OAK"],
                    ...
                }
                OR if team specified:
                {
                    "team": "BUF",
                    "bye_week": 9
                }
            },
            "meta": {...}
        }
    """
    try:
        conn = get_db_connection()

        # Get all weeks in season
        all_weeks_query = """
        SELECT DISTINCT week
        FROM games
        WHERE season = ? AND game_type = 'REG'
        ORDER BY week
        """
        all_weeks = [row[0] for row in conn.execute(all_weeks_query, [season]).fetchall()]

        if team:
            # Resolve team first
            team_result = resolve_team(team)
            if not team_result["ok"]:
                conn.close()
                return {
                    "ok": False,
                    "data": None,
                    "error": f"Could not resolve team: {team}",
                    "meta": {}
                }
            team_abbr = team_result["team"]

            # Get weeks team played
            query = """
            SELECT DISTINCT week
            FROM games
            WHERE season = ?
                AND (home_team = ? OR away_team = ?)
                AND game_type = 'REG'
            """
            weeks_played = [row[0] for row in conn.execute(query, [season, team_abbr, team_abbr]).fetchall()]
            weeks_played_set = set(weeks_played)
            conn.close()

            # Find bye week
            bye_week = None
            for week in all_weeks:
                if week not in weeks_played_set:
                    bye_week = week
                    break

            return {
                "ok": True,
                "data": {
                    "season": season,
                    "team": team_abbr,
                    "bye_week": bye_week,
                },
                "error": None,
                "meta": {
                    "source": "games table",
                    "note": "null if team has no bye week or data unavailable",
                }
            }
        else:
            # Get all teams in season
            teams_query = """
            SELECT DISTINCT home_team
            FROM games
            WHERE season = ? AND game_type = 'REG'
            """
            all_teams = [row[0] for row in conn.execute(teams_query, [season]).fetchall()]

            # Group teams by bye week
            bye_weeks = {}
            for team_abbr in all_teams:
                weeks_query = """
                SELECT DISTINCT week
                FROM games
                WHERE season = ?
                    AND (home_team = ? OR away_team = ?)
                    AND game_type = 'REG'
                """
                weeks_played = [row[0] for row in conn.execute(weeks_query, [season, team_abbr, team_abbr]).fetchall()]
                weeks_played_set = set(weeks_played)

                # Find bye week for this team
                for week in all_weeks:
                    if week not in weeks_played_set:
                        week_key = str(int(week))
                        if week_key not in bye_weeks:
                            bye_weeks[week_key] = []
                        bye_weeks[week_key].append(team_abbr)
                        break
            conn.close()

            bye_weeks = {
                week: sorted(teams)
                for week, teams in sorted(bye_weeks.items(), key=lambda item: int(item[0]))
            }

            return {
                "ok": True,
                "data": {
                    "season": season,
                    "bye_weeks": bye_weeks,
                },
                "error": None,
                "meta": {
                    "source": "games table",
                    "teams_count": len(set(t for teams in bye_weeks.values() for t in teams)),
                }
            }

    except Exception as e:
        return {
            "ok": False,
            "data": None,
            "error": f"Error fetching bye weeks: {str(e)}",
            "meta": {}
        }


def get_upcoming_games(
    team: str,
    season: int,
    from_week: Optional[int] = None
) -> Dict[str, Any]:
    """
    Get a team's games from a specified week onward.

    Args:
        team: Team name or abbreviation
        season: NFL season year
        from_week: Starting week (default: 1). Games from this week onward.

    Returns:
        {
            "ok": bool,
            "data": {
                "team": "BUF",
                "season": 2025,
                "from_week": 10,
                "games": [
                    {
                        "week": 10,
                        "opponent": "KC",
                        "location": "away",
                        "game_date": "2025-11-09",
                        "result": null
                    },
                    ...
                ]
            },
            "meta": {...}
        }
    """
    # Resolve team
    team_result = resolve_team(team)
    if not team_result["ok"]:
        return {
            "ok": False,
            "data": None,
            "error": f"Could not resolve team: {team}",
            "meta": {}
        }

    team_abbr = team_result["team"]
    if from_week is None:
        from_week = 1
    if from_week < 1 or from_week > 22:
        return {
            "ok": False,
            "data": None,
            "error": "from_week must be between 1 and 22",
            "meta": {},
        }

    try:
        conn = get_db_connection()

        query = """
        SELECT
            week,
            game_id,
            home_team,
            away_team,
            home_score,
            away_score,
            gameday
        FROM games
        WHERE season = ?
            AND (home_team = ? OR away_team = ?)
            AND game_type = 'REG'
            AND week >= ?
        ORDER BY week ASC
        """

        games = conn.execute(query, [season, team_abbr, team_abbr, from_week]).fetchall()
        conn.close()

        upcoming = []
        for row in games:
            week, game_id, home_team, away_team, home_score, away_score, gameday = row

            is_home = home_team == team_abbr
            opponent = away_team if is_home else home_team
            location = "home" if is_home else "away"
            team_score = home_score if is_home else away_score
            opp_score = away_score if is_home else home_score

            # Determine result
            result = None
            if team_score is not None and opp_score is not None:
                if team_score > opp_score:
                    result = "W"
                elif team_score < opp_score:
                    result = "L"
                else:
                    result = "T"

            upcoming.append({
                "week": int(week),
                "game_id": game_id,
                "opponent": opponent,
                "location": location,
                "game_date": gameday,
                "result": result,
                "team_score": team_score,
                "opponent_score": opp_score,
            })

        return {
            "ok": True,
            "data": {
                "team": team_abbr,
                "season": season,
                "from_week": from_week,
                "games": upcoming,
            },
            "error": None,
            "meta": {
                "source": "games table",
                "games_count": len(upcoming),
                "from_week_default": "1 when not provided",
            }
        }

    except Exception as e:
        return {
            "ok": False,
            "data": None,
            "error": f"Error fetching upcoming games: {str(e)}",
            "meta": {}
        }


# ============================================================================
# Phase 7C-lite: Fantasy Schedule Context
# ============================================================================

MISSING_FANTASY_CONTEXT = {
    "injuries": "Not available in this tool. Check NFL.com, ESPN, or your fantasy platform for current injury status.",
    "depth_chart": "Not available in this tool. Check the team's official depth chart or your fantasy platform.",
    "projections": "This is historical data only, not a projection. Use dedicated fantasy projection tools for week-to-week forecasts.",
}


def _period_usage_summary(weeks: List[Dict[str, Any]], label: str) -> Dict[str, Any]:
    """Summarize touches and PPR points for a period of weekly usage rows."""
    games = len(weeks)
    touches = sum(int(week.get("carries", 0)) + int(week.get("targets", 0)) for week in weeks)
    ppr_points = round(sum(float(week.get("fantasy_points_ppr", 0.0)) for week in weeks), 2)
    return {
        "weeks": label,
        "games": games,
        "touches": touches,
        "avg_touches": round(touches / games, 2) if games else 0.0,
        "ppr_points": ppr_points,
        "avg_ppr_per_game": round(ppr_points / games, 2) if games else 0.0,
    }


def _usage_trend_from_weekly_usage(weekly_usage: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compare weeks 1-8 against weeks 9-17 for touches and PPR trend."""
    early_weeks = [week for week in weekly_usage if 1 <= int(week.get("week", 0)) <= 8]
    late_weeks = [week for week in weekly_usage if 9 <= int(week.get("week", 0)) <= 17]
    early = _period_usage_summary(early_weeks, "1-8")
    late = _period_usage_summary(late_weeks, "9-17")

    touch_delta = round(late["avg_touches"] - early["avg_touches"], 2)
    ppr_delta = round(late["avg_ppr_per_game"] - early["avg_ppr_per_game"], 2)
    early_touch_baseline = early["avg_touches"]
    early_ppr_baseline = early["avg_ppr_per_game"]
    late_touch_baseline = late["avg_touches"]
    late_ppr_baseline = late["avg_ppr_per_game"]

    touch_pct = _pct_change(early_touch_baseline, late["avg_touches"])
    ppr_pct = _pct_change(early_ppr_baseline, late["avg_ppr_per_game"])
    touch_pct_value = touch_pct if touch_pct is not None else 0.0
    ppr_pct_value = ppr_pct if ppr_pct is not None else 0.0

    status = "stable"
    note = None
    if touch_delta >= 3.0 and ppr_delta >= 3.0 and (touch_pct_value >= 25.0 or ppr_pct_value >= 25.0):
        status = "trending_up"
        note = "Increased opportunity in second half"
    else:
        down_touch_delta = round(early["avg_touches"] - late["avg_touches"], 2)
        down_ppr_delta = round(early["avg_ppr_per_game"] - late["avg_ppr_per_game"], 2)
        down_touch_pct = _pct_change(late_touch_baseline, early["avg_touches"])
        down_ppr_pct = _pct_change(late_ppr_baseline, early["avg_ppr_per_game"])
        down_touch_pct_value = down_touch_pct if down_touch_pct is not None else 0.0
        down_ppr_pct_value = down_ppr_pct if down_ppr_pct is not None else 0.0
        if (
            down_touch_delta >= 3.0
            and down_ppr_delta >= 3.0
            and (down_touch_pct_value >= 25.0 or down_ppr_pct_value >= 25.0)
        ):
            status = "trending_down"
            note = "Declining usage late"

    early["status"] = status
    late["status"] = status
    return {
        "early_period": early,
        "late_period": late,
        "change": {
            "touch_delta": touch_delta,
            "touch_delta_pct": touch_pct,
            "ppr_delta": ppr_delta,
            "ppr_delta_pct": ppr_pct,
            "status": status,
            "note": note,
        },
    }


def _format_weekly_usage_for_context(weekly_usage: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize weekly usage rows for fantasy schedule context responses."""
    formatted = []
    for week in weekly_usage:
        total_td = int(week.get("tds", 0))
        formatted.append({
            "week": int(week.get("week", 0)),
            "opponent": week.get("opponent"),
            "carries": int(week.get("carries", 0)),
            "targets": int(week.get("targets", 0)),
            "receptions": int(week.get("receptions", 0)),
            "rushing_yards": int(week.get("rushing_yards", 0)),
            "receiving_yards": int(week.get("receiving_yards", 0)),
            "passing_yards": int(week.get("passing_yards", 0)),
            "total_td": total_td,
            "fantasy_points_ppr": float(week.get("fantasy_points_ppr", 0.0)),
        })
    return formatted


def get_fantasy_schedule_context(
    player_name: str,
    season: int,
    from_week: Optional[int] = None
) -> Dict[str, Any]:
    """
    Get a player's fantasy context: schedule, bye week, weekly usage, and trend.

    This combines historical fantasy usage with schedule context. It does not
    include injuries, depth charts, or projections.
    """
    player_result = resolve_player(player_name, season)
    if not player_result["ok"]:
        return {"ok": False, "data": None, "error": player_result["error"], "meta": {}}

    from_week_used = from_week if from_week is not None else 1
    if from_week_used < 1 or from_week_used > 22:
        return {"ok": False, "data": None, "error": "from_week must be between 1 and 22", "meta": {}}

    player_id = player_result["player_id"]
    canonical_name = player_result["name"]
    position = player_result["position"]
    team = player_result["team"]

    bye_result = get_bye_weeks(season, team)
    if not bye_result["ok"]:
        return {"ok": False, "data": None, "error": bye_result["error"], "meta": {"player_id": player_id}}

    schedule_result = get_team_schedule_context(team, season)
    if not schedule_result["ok"]:
        return {"ok": False, "data": None, "error": schedule_result["error"], "meta": {"player_id": player_id}}

    weekly_result = get_player_weekly_usage(canonical_name, season)
    if not weekly_result["ok"]:
        return {"ok": False, "data": None, "error": weekly_result["error"], "meta": {"player_id": player_id}}

    schedule_rows = schedule_result["data"]["schedule"]
    games_from_week = [
        row for row in schedule_rows
        if not row.get("bye") and int(row.get("week", 0)) >= from_week_used
    ]
    weekly_usage = _format_weekly_usage_for_context(weekly_result["data"])
    usage_trend = _usage_trend_from_weekly_usage(weekly_usage)

    source = weekly_result.get("meta", {}).get("source", "weekly")
    meta = {
        "source": "weekly table (2020-2024) + pbp_derived (2025)",
        "usage_source": source,
        "coverage": "Full season schedule for team",
        "from_week": from_week_used,
        "from_week_default": "1 when not provided",
    }
    if season == 2025:
        meta["2025_note"] = "Usage derived from play-by-play data"

    return {
        "ok": True,
        "data": {
            "player_id": player_id,
            "player_name": canonical_name,
            "position": position,
            "team": team,
            "season": season,
            "team_bye_week": bye_result["data"]["bye_week"],
            "games_from_week": games_from_week,
            "weekly_usage": weekly_usage,
            "usage_trend": usage_trend,
            "missing_context": dict(MISSING_FANTASY_CONTEXT),
        },
        "error": None,
        "meta": meta,
    }


def compare_fantasy_context(
    player_names: List[str],
    season: int,
    from_week: Optional[int] = None
) -> Dict[str, Any]:
    """
    Compare multiple players' fantasy schedule context side-by-side.
    """
    if not player_names:
        return {"ok": False, "data": None, "error": "player_names cannot be empty", "meta": {}}

    from_week_used = from_week if from_week is not None else 1
    contexts = []
    for player_name in player_names:
        result = get_fantasy_schedule_context(player_name, season, from_week=from_week_used)
        if result["ok"]:
            player_context = result["data"]
            contexts.append({
                "player_id": player_context["player_id"],
                "player_name": player_context["player_name"],
                "position": player_context["position"],
                "team": player_context["team"],
                "team_bye_week": player_context["team_bye_week"],
                "season": player_context["season"],
                "games_from_week": player_context["games_from_week"],
                "usage_trend": player_context["usage_trend"],
                "missing_context": player_context["missing_context"],
            })
        else:
            contexts.append({"player_name": player_name, "error": result.get("error", "Unknown error")})

    if all("error" in context for context in contexts):
        return {
            "ok": False,
            "data": None,
            "error": "Could not build fantasy context for any of the provided player names",
            "meta": {},
        }

    return {
        "ok": True,
        "data": contexts,
        "error": None,
        "meta": {
            "players_compared": len([context for context in contexts if "error" not in context]),
            "season": season,
            "from_week": from_week_used,
            "note": "Compare team bye weeks, schedules from the selected week, and usage trends. Game strength, injuries, depth charts, and projections are not available in this tool.",
        },
    }
