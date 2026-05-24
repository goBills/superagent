"""
Database query utilities for Superagent.

Safe, consistent query execution with JSON-serializable results.
Handles error handling and data type conversion.
"""

from typing import Dict, List, Any, Optional
import duckdb
from superagent.config import get_config

config = get_config()


def get_db_connection() -> duckdb.DuckDBPyConnection:
    """Get DuckDB connection."""
    return duckdb.connect(str(config.DATABASE_PATH))


def _serialize_value(value: Any) -> Any:
    """
    Convert value to JSON-serializable type.

    Handles DuckDB-specific types and None values.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, str)):
        return value
    # For any other types (e.g., numpy, date), convert to string
    return str(value)


def query_to_dict(sql: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Execute SQL query and return results as JSON-serializable dict.

    Args:
        sql: SQL query string
        params: Optional dict of parameters for parameterized queries

    Returns:
        {
            "ok": bool,
            "columns": [list of column names],
            "rows": [list of row dicts],
            "row_count": int,
            "error": str (if ok=false)
        }
    """
    try:
        conn = get_db_connection()

        if params:
            result = conn.execute(sql, params)
        else:
            result = conn.execute(sql)

        columns = [desc[0] for desc in result.description]
        rows = result.fetchall()
        conn.close()

        # Convert rows to list of dicts
        result_rows = []
        for row in rows:
            row_dict = {}
            for col_name, value in zip(columns, row):
                row_dict[col_name] = _serialize_value(value)
            result_rows.append(row_dict)

        return {
            "ok": True,
            "columns": columns,
            "rows": result_rows,
            "row_count": len(result_rows),
            "error": None
        }

    except Exception as e:
        return {
            "ok": False,
            "columns": [],
            "rows": [],
            "row_count": 0,
            "error": str(e)
        }


def get_team_games(team_abbr: str, season: int) -> Dict[str, Any]:
    """
    Get games where a team played.

    Args:
        team_abbr: Team abbreviation (e.g., "BUF")
        season: NFL season year

    Returns:
        {
            "ok": bool,
            "games": [list of game dicts],
            "error": str (if ok=false)
        }
    """
    sql = """
        SELECT DISTINCT
            game_id,
            season,
            week,
            home_team,
            away_team,
            CASE WHEN home_team = '{team_abbr}' THEN 'H' ELSE 'A' END AS home_away,
            game_date,
            result,
            points_home,
            points_away
        FROM games
        WHERE (home_team = ? OR away_team = ?)
          AND season = ?
        ORDER BY week
    """

    try:
        conn = get_db_connection()
        result = conn.execute(sql, [team_abbr, team_abbr, season]).fetchall()
        columns = ["game_id", "season", "week", "home_team", "away_team", "home_away", "game_date", "result", "points_home", "points_away"]

        games = []
        for row in result:
            games.append({
                col: _serialize_value(val)
                for col, val in zip(columns, row)
            })
        conn.close()

        return {
            "ok": True,
            "games": games,
            "error": None
        }

    except Exception as e:
        return {
            "ok": False,
            "games": [],
            "error": str(e)
        }


def get_player_stats(player_id: str, season: int) -> Dict[str, Any]:
    """
    Get player season totals from player_season_stats view.

    Args:
        player_id: Player ID
        season: NFL season year

    Returns:
        {
            "ok": bool,
            "stats": dict (single row) or None,
            "source": str ("weekly" or "pbp_derived"),
            "error": str (if ok=false)
        }
    """
    sql = """
        SELECT *
        FROM player_season_stats
        WHERE player_id = ?
          AND season = ?
    """

    try:
        conn = get_db_connection()
        query = conn.execute(sql, [player_id, season])
        result = query.fetchall()
        columns = [desc[0] for desc in query.description]

        if not result:
            conn.close()
            return {
                "ok": True,
                "stats": None,
                "source": None,
                "error": None
            }

        row = result[0]
        stats = {col: _serialize_value(val) for col, val in zip(columns, row)}

        # Determine source
        source = stats.get("source", "unknown")
        if source == "pbp_derived" or season == 2025:
            source = "pbp_derived"

        conn.close()

        return {
            "ok": True,
            "stats": stats,
            "source": source,
            "error": None
        }

    except Exception as e:
        return {
            "ok": False,
            "stats": None,
            "source": None,
            "error": str(e)
        }


def get_game_team_stats(game_id: str, team_abbr: str) -> Dict[str, Any]:
    """
    Get team stats for a specific game from game_team_summary view.

    Args:
        game_id: Game ID
        team_abbr: Team abbreviation

    Returns:
        {
            "ok": bool,
            "stats": dict or None,
            "error": str (if ok=false)
        }
    """
    sql = """
        SELECT *
        FROM game_team_summary
        WHERE game_id = ?
          AND team = ?
    """

    try:
        conn = get_db_connection()
        query = conn.execute(sql, [game_id, team_abbr])
        result = query.fetchall()

        if not result:
            conn.close()
            return {
                "ok": True,
                "stats": None,
                "error": None
            }

        columns = [desc[0] for desc in query.description]
        row = result[0]
        stats = {col: _serialize_value(val) for col, val in zip(columns, row)}

        conn.close()

        return {
            "ok": True,
            "stats": stats,
            "error": None
        }

    except Exception as e:
        return {
            "ok": False,
            "stats": None,
            "error": str(e)
        }


def get_team_week_stats(team_abbr: str, season: int, week: int) -> Dict[str, Any]:
    """
    Get team EPA stats for a specific week from team_week_epa view.

    Args:
        team_abbr: Team abbreviation
        season: NFL season year
        week: Week number

    Returns:
        {
            "ok": bool,
            "stats": dict or None,
            "error": str (if ok=false)
        }
    """
    sql = """
        SELECT *
        FROM team_week_epa
        WHERE team = ?
          AND season = ?
          AND week = ?
    """

    try:
        conn = get_db_connection()
        query = conn.execute(sql, [team_abbr, season, week])
        result = query.fetchall()

        if not result:
            conn.close()
            return {
                "ok": True,
                "stats": None,
                "error": None
            }

        columns = [desc[0] for desc in query.description]
        row = result[0]
        stats = {col: _serialize_value(val) for col, val in zip(columns, row)}

        conn.close()

        return {
            "ok": True,
            "stats": stats,
            "error": None
        }

    except Exception as e:
        return {
            "ok": False,
            "stats": None,
            "error": str(e)
        }
