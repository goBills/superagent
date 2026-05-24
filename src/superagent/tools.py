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
