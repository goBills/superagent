"""
ESPN fantasy football league ingestion.

This module keeps ESPN as an optional live integration. It writes durable league,
roster, and draft-pick context into the product DB so draft tools can operate on
stored data even when ESPN cookies or network access are unavailable.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from superagent.canonical_resolution import auto_map_external_player
from superagent.db import SessionLocal
from superagent.models import (
    League,
    LeagueDraftPick,
    LeagueExternalSource,
    LeagueRosterPlayer,
    LeagueSettings,
)


class ESPNIntegrationError(RuntimeError):
    """Raised when ESPN ingestion cannot proceed."""


def fetch_espn_league(
    league_id: int,
    season: int,
    espn_s2: str | None = None,
    swid: str | None = None,
) -> Any:
    """Fetch an ESPN fantasy football league using espn-api."""
    try:
        from espn_api.football import League as ESPNLeague
    except ImportError as exc:
        raise ESPNIntegrationError("espn-api is not installed") from exc

    kwargs: dict[str, Any] = {"league_id": league_id, "year": season}
    if espn_s2:
        kwargs["espn_s2"] = espn_s2
    if swid:
        kwargs["swid"] = swid
    return ESPNLeague(**kwargs)


def _get_attr(obj: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if isinstance(obj, dict) and name in obj:
            return obj[name]
        if hasattr(obj, name):
            return getattr(obj, name)
    return default


def _scoring_to_ppr_type(value: Any) -> str:
    text = str(value or "").lower()
    if "half" in text or "0.5" in text:
        return "half_ppr"
    if "ppr" in text or "point" in text:
        return "ppr"
    if text in {"standard", "0"}:
        return "standard"
    return "ppr"


def _settings_from_espn(espn_league: Any) -> dict[str, Any]:
    settings = _get_attr(espn_league, "settings", default={})
    scoring = _get_attr(settings, "scoring_format", "scoringFormat", "ppr_type", default=None)
    size = _get_attr(settings, "team_count", "team_count", "num_teams", default=None)
    if size is None:
        teams = _get_attr(espn_league, "teams", default=[])
        size = len(teams) if teams else 12
    return {
        "ppr_type": _scoring_to_ppr_type(scoring),
        "num_teams": int(size or 12),
        "roster_spots": int(_get_attr(settings, "roster_size", "roster_spots", default=16) or 16),
        "qb_slots": int(_get_attr(settings, "qb_slots", default=1) or 1),
        "rb_slots": int(_get_attr(settings, "rb_slots", default=2) or 2),
        "wr_slots": int(_get_attr(settings, "wr_slots", default=2) or 2),
        "te_slots": int(_get_attr(settings, "te_slots", default=1) or 1),
        "flex_slots": int(_get_attr(settings, "flex_slots", default=1) or 1),
        "superflex_slots": int(_get_attr(settings, "superflex_slots", default=0) or 0),
        "bench_spots": int(_get_attr(settings, "bench_spots", default=6) or 6),
        "taxi_spots": int(_get_attr(settings, "taxi_spots", default=0) or 0),
        "passing_td_points": float(_get_attr(settings, "passing_td_points", default=4.0) or 4.0),
        "rushing_td_points": float(_get_attr(settings, "rushing_td_points", default=6.0) or 6.0),
        "receiving_td_points": float(_get_attr(settings, "receiving_td_points", default=6.0) or 6.0),
        "pass_yards_per_point": float(_get_attr(settings, "pass_yards_per_point", default=25.0) or 25.0),
        "rush_yards_per_point": float(_get_attr(settings, "rush_yards_per_point", default=10.0) or 10.0),
        "receiving_yards_per_point": float(_get_attr(settings, "receiving_yards_per_point", default=10.0) or 10.0),
    }


def _apply_settings(settings: LeagueSettings, values: dict[str, Any]) -> None:
    for key, value in values.items():
        setattr(settings, key, value)


def _player_name(player: Any) -> str | None:
    return _get_attr(player, "name", "playerName", "full_name", "fullName", default=None)


def _player_position(player: Any) -> str | None:
    position = _get_attr(player, "position", "proTeam", default=None)
    if position is None:
        return None
    return str(position).upper()


def _team_name(team: Any) -> str:
    return str(_get_attr(team, "team_name", "teamName", "name", default="Unknown Team"))


def _pick_player(pick: Any) -> Any:
    return _get_attr(pick, "player", "playerName", default=pick)


def _pick_name(pick: Any) -> str | None:
    player = _pick_player(pick)
    if isinstance(player, str):
        return player
    return _player_name(player) or _get_attr(pick, "playerName", "player_name", default=None)


def ingest_espn_league(
    espn_league_id: int,
    season: int,
    user_id: int,
    espn_s2: str | None = None,
    swid: str | None = None,
    db: Session | None = None,
    espn_league: Any | None = None,
) -> dict[str, Any]:
    """Fetch and store ESPN league settings, current rosters, and draft picks."""
    owns_session = db is None
    db = db or SessionLocal()
    try:
        espn_league = espn_league or fetch_espn_league(
            league_id=espn_league_id,
            season=season,
            espn_s2=espn_s2,
            swid=swid,
        )
        settings_values = _settings_from_espn(espn_league)
        settings_obj = _get_attr(espn_league, "settings", default={})
        league_name = str(_get_attr(settings_obj, "name", "league_name", default=f"ESPN {espn_league_id}"))

        external = (
            db.query(LeagueExternalSource)
            .filter(
                LeagueExternalSource.source == "espn",
                LeagueExternalSource.external_league_id == str(espn_league_id),
                LeagueExternalSource.season == season,
            )
            .first()
        )
        if external:
            league = db.query(League).filter(League.id == external.league_id).first()
        else:
            league = None
        if league is None:
            league = League(user_id=user_id, league_name=league_name, league_type="snake")
            db.add(league)
            db.flush()
        league.league_name = league_name
        if league.settings is None:
            league.settings = LeagueSettings(league_id=league.id)
        _apply_settings(league.settings, settings_values)

        if external is None:
            external = LeagueExternalSource(
                league_id=league.id,
                source="espn",
                external_league_id=str(espn_league_id),
                season=season,
            )
            db.add(external)
        external.metadata_json = json.dumps({"league_name": league_name, "season": season})

        db.query(LeagueRosterPlayer).filter(
            LeagueRosterPlayer.league_id == league.id,
            LeagueRosterPlayer.season == season,
        ).delete()
        db.query(LeagueDraftPick).filter(
            LeagueDraftPick.league_id == league.id,
            LeagueDraftPick.season == season,
        ).delete()
        db.flush()

        roster_count = 0
        roster_review = 0
        for team in _get_attr(espn_league, "teams", default=[]) or []:
            team_name = _team_name(team)
            for player in _get_attr(team, "roster", default=[]) or []:
                name = _player_name(player)
                if not name:
                    continue
                position = _player_position(player)
                mapping = auto_map_external_player("espn", season, name, position=position, db=db)
                if not mapping["ok"]:
                    roster_review += 1
                db.add(
                    LeagueRosterPlayer(
                        league_id=league.id,
                        season=season,
                        fantasy_team_name=team_name,
                        roster_slot=_get_attr(player, "slot_position", "lineupSlot", default=None),
                        source_player_name=name,
                        position=position,
                        canonical_player_id=mapping.get("canonical_player_id"),
                        mapping_status="mapped" if mapping["ok"] else "needs_review",
                    )
                )
                roster_count += 1

        draft_count = 0
        draft_review = 0
        for index, pick in enumerate(_get_attr(espn_league, "draft", "draft_picks", default=[]) or [], start=1):
            name = _pick_name(pick)
            if not name:
                continue
            player = _pick_player(pick)
            position = _player_position(player)
            mapping = auto_map_external_player("espn", season, name, position=position, db=db)
            if not mapping["ok"]:
                draft_review += 1
            db.add(
                LeagueDraftPick(
                    league_id=league.id,
                    season=season,
                    round_num=_get_attr(pick, "round_num", "round", default=None),
                    pick_num=_get_attr(pick, "pick_num", "pick", default=index),
                    fantasy_team_name=_get_attr(pick, "team", "team_name", default=None),
                    source_player_name=name,
                    position=position,
                    canonical_player_id=mapping.get("canonical_player_id"),
                    mapping_status="mapped" if mapping["ok"] else "needs_review",
                )
            )
            draft_count += 1

        db.commit()
        return {
            "ok": True,
            "league_id": league.id,
            "source": "espn",
            "external_league_id": str(espn_league_id),
            "season": season,
            "league_name": league.league_name,
            "settings": settings_values,
            "roster_players": roster_count,
            "roster_needing_review": roster_review,
            "draft_picks": draft_count,
            "draft_needing_review": draft_review,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        if owns_session:
            db.close()
