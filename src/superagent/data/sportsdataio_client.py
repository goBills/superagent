"""Small SportsDataIO client used for read-only access probes.

The API key is always sent as a request header, not as a query parameter, so it
does not appear in URLs, access logs, or exception text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from superagent.config import get_config


SPORTSDATAIO_BASE_URL = "https://api.sportsdata.io/v3/nfl"


@dataclass(frozen=True)
class SportsDataIOEndpoint:
    """One endpoint worth probing during vendor evaluation."""

    name: str
    path: str
    description: str


TRIAL_PROBE_ENDPOINTS: tuple[SportsDataIOEndpoint, ...] = (
    SportsDataIOEndpoint(
        name="players",
        path="/scores/json/Players",
        description="Current full player details, teams, positions, and injury fields.",
    ),
    SportsDataIOEndpoint(
        name="byes",
        path="/scores/json/Byes/{season}",
        description="Season bye weeks by team.",
    ),
    SportsDataIOEndpoint(
        name="depth_charts_all",
        path="/scores/json/DepthChartsAll",
        description="Current team depth charts, including non-active roster statuses expected to return.",
    ),
    SportsDataIOEndpoint(
        name="injured_players",
        path="/projections/json/InjuredPlayers",
        description="Low-latency injured player feed.",
    ),
    SportsDataIOEndpoint(
        name="season_projections",
        path="/projections/json/PlayerSeasonProjectionStats/{season}",
        description="Season-long fantasy projections, usually including ADP fields.",
    ),
)


class SportsDataIOError(RuntimeError):
    """Raised when SportsDataIO access is not configured or a request fails."""


class SportsDataIOClient:
    """Thin HTTP client for SportsDataIO NFL endpoints."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = SPORTSDATAIO_BASE_URL,
        timeout: int = 30,
        session: requests.Session | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else get_config().SPORTSDATAIO_API_KEY
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        if not self.api_key or "your_" in self.api_key:
            raise SportsDataIOError("SPORTSDATAIO_API_KEY is not configured")

    def get_json(self, path: str, *, season: int | None = None) -> Any:
        """GET a SportsDataIO path and return decoded JSON."""
        formatted_path = path.format(season=season) if season is not None else path
        url = f"{self.base_url}/{formatted_path.lstrip('/')}"
        response = self.session.get(
            url,
            headers={"Ocp-Apim-Subscription-Key": self.api_key},
            timeout=self.timeout,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise SportsDataIOError(_format_http_error(response)) from exc
        return response.json()


def _format_http_error(response: requests.Response) -> str:
    """Return a short failure message without including secrets."""
    body = (response.text or "").strip().replace("\n", " ")
    if len(body) > 240:
        body = f"{body[:240]}..."
    return f"SportsDataIO request failed with {response.status_code}: {body}"


def sample_records(payload: Any, *, limit: int = 3) -> list[dict[str, Any]]:
    """Return a few compact records from a JSON payload for probe output."""
    rows: list[Any]
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = [payload]
    else:
        rows = []

    samples: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        samples.append(_compact_record(row))
        if len(samples) >= limit:
            break
    return samples


def _compact_record(row: dict[str, Any]) -> dict[str, Any]:
    """Keep probe output readable by preferring fields relevant to fantasy context."""
    if "Offense" in row or "Defense" in row or "SpecialTeams" in row:
        offense = row.get("Offense") if isinstance(row.get("Offense"), list) else []
        defense = row.get("Defense") if isinstance(row.get("Defense"), list) else []
        special_teams = row.get("SpecialTeams") if isinstance(row.get("SpecialTeams"), list) else []
        return {
            "TeamID": row.get("TeamID"),
            "offense_count": len(offense),
            "defense_count": len(defense),
            "special_teams_count": len(special_teams),
            "offense_sample": [_compact_depth_entry(entry) for entry in offense[:5] if isinstance(entry, dict)],
        }

    preferred_keys = [
        "PlayerID",
        "FantasyDataPlayerID",
        "SportsDataID",
        "Name",
        "FirstName",
        "LastName",
        "Team",
        "Position",
        "FantasyPosition",
        "Status",
        "InjuryStatus",
        "InjuryBodyPart",
        "InjuryNotes",
        "ByeWeek",
        "Week",
        "AverageDraftPosition",
        "AverageDraftPositionPPR",
        "ProjectedFantasyPoints",
        "FantasyPoints",
        "DepthOrder",
        "DepthDisplayOrder",
    ]
    compact = {key: row.get(key) for key in preferred_keys if key in row}
    if compact:
        return compact
    return {key: row.get(key) for key in list(row.keys())[:12]}


def _compact_depth_entry(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "PlayerID": row.get("PlayerID"),
        "Name": row.get("Name"),
        "Position": row.get("Position"),
        "DepthOrder": row.get("DepthOrder"),
        "Updated": row.get("Updated"),
    }
