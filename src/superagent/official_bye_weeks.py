"""Official NFL bye-week reference data.

This module intentionally keeps small, static schedule facts out of the
analytics warehouse so draft planning can use the current NFL schedule before
nflverse publishes a refreshed games file.
"""

from __future__ import annotations

from collections import defaultdict

OFFICIAL_BYE_WEEK_SOURCE = "nfl.com"

OFFICIAL_BYE_WEEKS_BY_TEAM: dict[int, dict[str, int]] = {
    2026: {
        "CAR": 5,
        "KC": 5,
        "CIN": 6,
        "DET": 6,
        "MIA": 6,
        "MIN": 6,
        "BUF": 7,
        "JAX": 7,
        "LAC": 7,
        "WAS": 7,
        "HOU": 8,
        "NO": 8,
        "NYG": 8,
        "SF": 8,
        "PIT": 9,
        "TEN": 9,
        "CHI": 10,
        "DEN": 10,
        "PHI": 10,
        "TB": 10,
        "ATL": 11,
        "CLE": 11,
        "GB": 11,
        "LAR": 11,
        "NE": 11,
        "SEA": 11,
        "BAL": 13,
        "IND": 13,
        "LV": 13,
        "NYJ": 13,
        "ARI": 14,
        "DAL": 14,
    }
}


def latest_official_bye_week_season() -> int | None:
    """Return the newest season with checked-in official bye-week data."""
    if not OFFICIAL_BYE_WEEKS_BY_TEAM:
        return None
    return max(OFFICIAL_BYE_WEEKS_BY_TEAM)


def has_official_bye_weeks(season: int) -> bool:
    return season in OFFICIAL_BYE_WEEKS_BY_TEAM


def official_bye_week_for_team(season: int, team: str) -> int | None:
    return OFFICIAL_BYE_WEEKS_BY_TEAM.get(season, {}).get(team.upper())


def official_bye_weeks_by_week(season: int) -> dict[str, list[str]]:
    grouped: dict[int, list[str]] = defaultdict(list)
    for team, week in OFFICIAL_BYE_WEEKS_BY_TEAM.get(season, {}).items():
        grouped[week].append(team)
    return {str(week): sorted(teams) for week, teams in sorted(grouped.items())}
