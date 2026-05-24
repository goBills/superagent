"""
Name resolution for players and teams.

Fuzzy matching uses roster full names first so 2025 play-by-play-derived
stats can still resolve from names like "Josh Allen" even when the stat row
uses an abbreviated play-by-play name such as "J.Allen".
"""

from typing import Any, Dict

import duckdb
from rapidfuzz import fuzz

from superagent.config import get_config

config = get_config()


def get_db_connection() -> duckdb.DuckDBPyConnection:
    """Get a DuckDB connection."""
    return duckdb.connect(str(config.DATABASE_PATH))


TEAM_ALIASES = {
    "buffalo": "BUF",
    "bills": "BUF",
    "new england": "NE",
    "patriots": "NE",
    "new york jets": "NYJ",
    "jets": "NYJ",
    "miami": "MIA",
    "dolphins": "MIA",
    "kansas city": "KC",
    "chiefs": "KC",
    "denver": "DEN",
    "broncos": "DEN",
    "los angeles chargers": "LAC",
    "la chargers": "LAC",
    "chargers": "LAC",
    "las vegas": "LV",
    "raiders": "LV",
    "pittsburgh": "PIT",
    "steelers": "PIT",
    "baltimore": "BAL",
    "ravens": "BAL",
    "philadelphia": "PHI",
    "eagles": "PHI",
    "dallas": "DAL",
    "cowboys": "DAL",
    "washington": "WAS",
    "commanders": "WAS",
    "new york giants": "NYG",
    "giants": "NYG",
    "green bay": "GB",
    "packers": "GB",
    "detroit": "DET",
    "lions": "DET",
    "chicago": "CHI",
    "bears": "CHI",
    "minnesota": "MIN",
    "vikings": "MIN",
    "tampa bay": "TB",
    "buccaneers": "TB",
    "bucs": "TB",
    "new orleans": "NO",
    "saints": "NO",
    "atlanta": "ATL",
    "falcons": "ATL",
    "carolina": "CAR",
    "panthers": "CAR",
    "san francisco": "SF",
    "49ers": "SF",
    "niners": "SF",
    "seattle": "SEA",
    "seahawks": "SEA",
    "los angeles rams": "LA",
    "la rams": "LA",
    "rams": "LA",
    "arizona": "ARI",
    "cardinals": "ARI",
    "tennessee": "TEN",
    "titans": "TEN",
    "houston": "HOU",
    "texans": "HOU",
    "jacksonville": "JAX",
    "jaguars": "JAX",
    "indianapolis": "IND",
    "colts": "IND",
    "cincinnati": "CIN",
    "bengals": "CIN",
    "cleveland": "CLE",
    "browns": "CLE",
}


def _standard_response(ok: bool, **kwargs: Any) -> Dict[str, Any]:
    payload = {"ok": ok, "error": None}
    payload.update(kwargs)
    if not ok and "error" not in kwargs:
        payload["error"] = "Unknown error"
    return payload


def resolve_team(name: str) -> Dict[str, Any]:
    """Resolve team name, alias, or abbreviation to an nflverse team code."""
    if not name or not name.strip():
        return {"ok": False, "team": None, "aliases_matched": [], "error": "Team name cannot be empty"}

    normalized = name.lower().strip()
    team_code = name.upper().strip()
    valid_codes = set(TEAM_ALIASES.values())

    if team_code in valid_codes:
        return {"ok": True, "team": team_code, "aliases_matched": [name], "error": None}

    if normalized in TEAM_ALIASES:
        return {
            "ok": True,
            "team": TEAM_ALIASES[normalized],
            "aliases_matched": [normalized],
            "error": None,
        }

    best_alias = None
    best_score = 0
    for alias, code in TEAM_ALIASES.items():
        score = fuzz.token_set_ratio(normalized, alias)
        if score > best_score:
            best_score = score
            best_alias = (alias, code)

    if best_alias and best_score >= 80:
        alias, code = best_alias
        return {
            "ok": True,
            "team": code,
            "aliases_matched": [alias],
            "fuzzy_score": best_score,
            "error": None,
        }

    return {
        "ok": False,
        "team": None,
        "aliases_matched": [],
        "error": f"Could not resolve team '{name}' to a known NFL team",
    }


def _player_candidates(season: int):
    """Return one row per player for a season, preferring full roster names."""
    conn = get_db_connection()
    try:
        rows = conn.execute(
            """
            WITH roster_players AS (
                SELECT
                    season,
                    gsis_id AS player_id,
                    full_name AS display_name,
                    football_name,
                    position,
                    team,
                    'rosters' AS name_source
                FROM rosters
                WHERE season = ?
                  AND gsis_id IS NOT NULL
                  AND full_name IS NOT NULL
            ),
            weekly_players AS (
                SELECT
                    season,
                    player_id,
                    player_display_name AS display_name,
                    player_name AS football_name,
                    position,
                    recent_team AS team,
                    'weekly' AS name_source
                FROM weekly
                WHERE season = ?
                  AND player_id IS NOT NULL
                  AND player_display_name IS NOT NULL
            ),
            stat_players AS (
                SELECT
                    season,
                    player_id,
                    player_name AS display_name,
                    player_name AS football_name,
                    NULL AS position,
                    team,
                    source AS name_source
                FROM player_season_stats
                WHERE season = ?
                  AND player_id IS NOT NULL
                  AND player_name IS NOT NULL
            ),
            combined AS (
                SELECT * FROM roster_players
                UNION ALL
                SELECT * FROM weekly_players
                UNION ALL
                SELECT * FROM stat_players
            ),
            ranked AS (
                SELECT
                    *,
                    ROW_NUMBER() OVER (
                        PARTITION BY player_id
                        ORDER BY
                            CASE name_source
                                WHEN 'rosters' THEN 1
                                WHEN 'weekly' THEN 2
                                ELSE 3
                            END,
                            display_name
                    ) AS row_num
                FROM combined
            )
            SELECT player_id, display_name, football_name, position, team, name_source
            FROM ranked
            WHERE row_num = 1
            ORDER BY display_name
            """,
            [season, season, season],
        ).fetchall()
        return rows
    finally:
        conn.close()


def resolve_player(name: str, season: int) -> Dict[str, Any]:
    """Resolve a player name to a GSIS player id and metadata."""
    if not name or not name.strip():
        return {"ok": False, "error": "Player name cannot be empty"}

    if season < 2020 or season > 2025:
        return {"ok": False, "error": f"Season {season} out of supported range (2020-2025)"}

    try:
        candidates = _player_candidates(season)
    except Exception as exc:
        return {"ok": False, "error": f"Database error: {exc}"}

    if not candidates:
        return {"ok": False, "error": f"No players found for season {season}"}

    needle = name.lower().strip()
    exact_matches = [
        row for row in candidates
        if str(row[1]).lower() == needle or (row[2] and str(row[2]).lower() == needle)
    ]
    if exact_matches:
        player_id, display_name, _, position, team, source = exact_matches[0]
        return {
            "ok": True,
            "player_id": str(player_id),
            "name": str(display_name),
            "position": str(position) if position else None,
            "team": str(team) if team else None,
            "name_source": str(source),
            "error": None,
        }

    scored = []
    for row in candidates:
        player_id, display_name, football_name, position, team, source = row
        display_score = fuzz.token_set_ratio(needle, str(display_name).lower())
        football_score = fuzz.token_set_ratio(needle, str(football_name).lower()) if football_name else 0
        score = max(display_score, football_score)
        scored.append((score, player_id, display_name, position, team, source))

    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, player_id, display_name, position, team, source = scored[0]

    if best_score >= 80:
        return {
            "ok": True,
            "player_id": str(player_id),
            "name": str(display_name),
            "position": str(position) if position else None,
            "team": str(team) if team else None,
            "name_source": str(source),
            "fuzzy_score": best_score,
            "error": None,
        }

    return {
        "ok": False,
        "error": f"Could not resolve player '{name}' for season {season} (best match score: {best_score})",
    }


def search_players(partial_name: str, season: int, limit: int = 10) -> Dict[str, Any]:
    """Fuzzy search for player candidates."""
    if not partial_name or not partial_name.strip():
        return {"ok": False, "candidates": [], "error": "Search name cannot be empty"}

    if season < 2020 or season > 2025:
        return {"ok": False, "candidates": [], "error": f"Season {season} out of supported range (2020-2025)"}

    try:
        candidates = _player_candidates(season)
    except Exception as exc:
        return {"ok": False, "candidates": [], "error": f"Database error: {exc}"}

    needle = partial_name.lower().strip()
    scored = []
    for player_id, display_name, football_name, position, team, source in candidates:
        display_score = fuzz.token_set_ratio(needle, str(display_name).lower())
        football_score = fuzz.token_set_ratio(needle, str(football_name).lower()) if football_name else 0
        score = max(display_score, football_score)
        if score > 0:
            scored.append({
                "player_id": str(player_id),
                "name": str(display_name),
                "position": str(position) if position else None,
                "team": str(team) if team else None,
                "name_source": str(source),
                "score": score,
            })

    scored.sort(key=lambda row: row["score"], reverse=True)
    return {"ok": True, "candidates": scored[:limit], "error": None}
