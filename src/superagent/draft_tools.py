"""
Draft decision-support tools.

These tools combine persisted league settings, imported draft market data, and
canonical identity. They are research/decision support, not projections.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from superagent.canonical_resolution import resolve_to_canonical
from superagent.db import SessionLocal
from superagent.draft_value import adjust_draft_value
from superagent.models import DraftPlayerMarket, League, LeagueDraftPick, LeagueSettings

ELITE_DST_EFFECTIVE_RANK_CUTOFF = 140


def _response(ok: bool, data: Any = None, error: str | None = None, meta: dict | None = None) -> dict:
    return {"ok": ok, "data": data, "error": error, "meta": meta or {}}


def _get_league(db: Session, league_id: int) -> League | None:
    return db.query(League).filter(League.id == league_id).first()


def _league_settings(league: League) -> LeagueSettings:
    return league.settings or LeagueSettings(league_id=league.id)


def _latest_market_season(db: Session) -> int | None:
    row = db.query(DraftPlayerMarket.season).order_by(DraftPlayerMarket.season.desc()).first()
    return int(row[0]) if row else None


def _drafted_ids(db: Session, league_id: int, season: int, extra_ids: list[str] | None = None) -> set[str]:
    ids = {
        row[0]
        for row in db.query(LeagueDraftPick.canonical_player_id)
        .filter(
            LeagueDraftPick.league_id == league_id,
            LeagueDraftPick.season == season,
            LeagueDraftPick.canonical_player_id.isnot(None),
        )
        .all()
    }
    ids.update(extra_ids or [])
    return ids


def _market_rows(
    db: Session,
    season: int,
    source: str | None = None,
    position: str | None = None,
) -> list[DraftPlayerMarket]:
    query = db.query(DraftPlayerMarket).filter(DraftPlayerMarket.season == season)
    if source:
        query = query.filter(DraftPlayerMarket.source == source)
    if position:
        query = query.filter(DraftPlayerMarket.position == position.upper())
    return query.all()


def _effective_rank(market: DraftPlayerMarket) -> tuple[float | None, str | None]:
    if market.adp is not None:
        return market.adp, "ADP"
    if market.avg_rank is not None:
        return market.avg_rank, "avg rank"
    if market.overall_rank is not None:
        return market.overall_rank, "overall rank"
    return None, None


def _is_explicit_special_teams_request(position: str | None) -> bool:
    return bool(position and position.upper() in {"K", "DST", "D/ST", "DEF"})


def _passes_default_position_filter(market: DraftPlayerMarket, payload: dict[str, Any], position: str | None) -> bool:
    if _is_explicit_special_teams_request(position):
        return True
    market_position = (market.position or "").upper()
    if market_position == "K":
        return False
    if market_position in {"DST", "D/ST", "DEF"}:
        effective_rank = payload["effective_rank"]
        value_delta = payload["value_delta"]
        return (
            effective_rank is not None
            and effective_rank <= ELITE_DST_EFFECTIVE_RANK_CUTOFF
            and value_delta is not None
            and value_delta > 0
        )
    return True


def _market_payload(market: DraftPlayerMarket, settings: LeagueSettings) -> dict[str, Any]:
    adjusted = adjust_draft_value(market, settings)
    effective_rank, rank_source = _effective_rank(market)
    value_delta = None
    if market.adp is not None and market.ecr is not None:
        value_delta = round(float(market.adp) - float(market.ecr), 3)
    elif effective_rank is not None and market.ecr is not None:
        value_delta = round(float(effective_rank) - float(market.ecr), 3)
    if value_delta is None:
        value_delta = adjusted["league_adjustment"]
    else:
        value_delta = round(value_delta + adjusted["league_adjustment"], 3)
    return {
        "canonical_player_id": market.canonical_player_id,
        "player_name": market.source_player_name,
        "position": market.position,
        "team": market.team,
        "bye_week": market.bye_week,
        "adp": market.adp,
        "effective_rank": effective_rank,
        "rank_source": rank_source,
        "draft_position": effective_rank,
        "draft_position_source": rank_source,
        "ecr": market.ecr,
        "avg_rank": market.avg_rank,
        "value": market.value,
        "injury_risk": market.injury_risk,
        "adjusted_value": adjusted["adjusted_value"],
        "league_adjustment": adjusted["league_adjustment"],
        "value_delta": value_delta,
    }


def find_draft_targets(
    league_id: int,
    position: str | None = None,
    min_effective_rank: float | None = None,
    max_effective_rank: float | None = None,
    min_adp: float | None = None,
    max_adp: float | None = None,
    min_value_delta: float | None = None,
    bye_week_filters: list[int] | None = None,
    season: int | None = None,
    source: str | None = None,
    limit: int = 20,
) -> dict:
    """Find draft targets for a stored league using imported market data."""
    if min_effective_rank is None:
        min_effective_rank = min_adp
    if max_effective_rank is None:
        max_effective_rank = max_adp

    with SessionLocal() as db:
        league = _get_league(db, league_id)
        if league is None:
            return _response(False, error=f"League {league_id} not found")
        season = season or _latest_market_season(db)
        if season is None:
            return _response(False, error="No draft market data imported")
        settings = _league_settings(league)
        drafted = _drafted_ids(db, league_id, season)
        rows = []
        for market in _market_rows(db, season, source=source, position=position):
            if market.canonical_player_id in drafted:
                continue
            effective_rank, _ = _effective_rank(market)
            if min_effective_rank is not None and (effective_rank is None or effective_rank < min_effective_rank):
                continue
            if max_effective_rank is not None and (effective_rank is None or effective_rank > max_effective_rank):
                continue
            if bye_week_filters and market.bye_week in set(bye_week_filters):
                continue
            payload = _market_payload(market, settings)
            if min_value_delta is not None and payload["value_delta"] < min_value_delta:
                continue
            if not _passes_default_position_filter(market, payload, position):
                continue
            rows.append(payload)
        rows.sort(key=lambda row: (row["value_delta"], row["adjusted_value"]), reverse=True)
        limit = max(1, min(limit, 100))
        return _response(
            True,
            data=rows[:limit],
            meta={
                "league_id": league_id,
                "season": season,
                "source": source,
                "position": position,
                "min_effective_rank": min_effective_rank,
                "max_effective_rank": max_effective_rank,
                "min_adp": min_adp,
                "max_adp": max_adp,
                "rank_semantics": "Effective Rank uses ADP when available, otherwise avg rank, otherwise overall rank.",
                "default_special_teams_filter": (
                    "K excluded unless requested. D/ST excluded unless requested or effective rank <= "
                    f"{ELITE_DST_EFFECTIVE_RANK_CUTOFF} with positive value delta."
                ),
                "excluded_drafted_players": len(drafted),
                "historical_research_only": True,
            },
        )


def compare_draft_options(
    league_id: int,
    player_names: list[str],
    season: int | None = None,
    source: str | None = None,
) -> dict:
    """Compare specific draft options in a league context."""
    if not player_names:
        return _response(False, error="player_names is required")
    with SessionLocal() as db:
        league = _get_league(db, league_id)
        if league is None:
            return _response(False, error=f"League {league_id} not found")
        season = season or _latest_market_season(db)
        if season is None:
            return _response(False, error="No draft market data imported")
        settings = _league_settings(league)
        rows = []
        for name in player_names:
            resolution = resolve_to_canonical(name, season, db=db)
            query = db.query(DraftPlayerMarket).filter(DraftPlayerMarket.season == season)
            if source:
                query = query.filter(DraftPlayerMarket.source == source)
            if resolution["ok"]:
                query = query.filter(
                    DraftPlayerMarket.canonical_player_id == resolution["canonical_player_id"],
                )
            else:
                query = query.filter(DraftPlayerMarket.source_player_name == name)
            market = query.first()
            if market is None:
                error = resolution.get("error") if not resolution["ok"] else "No draft market row found"
                rows.append({"player_name": name, "ok": False, "error": error})
                continue
            payload = _market_payload(market, settings)
            payload["ok"] = True
            rows.append(payload)
        rows.sort(key=lambda row: row.get("adjusted_value", -999), reverse=True)
        return _response(
            True,
            data=rows,
            meta={"league_id": league_id, "season": season, "historical_research_only": True},
        )


def get_draft_context(
    league_id: int,
    drafted_player_ids: list[str] | None = None,
    season: int | None = None,
    source: str | None = None,
) -> dict:
    """Summarize league settings, draft progress, and top available values."""
    targets = find_draft_targets(
        league_id=league_id,
        season=season,
        source=source,
        limit=10,
    )
    if not targets["ok"]:
        return targets
    with SessionLocal() as db:
        league = _get_league(db, league_id)
        settings = _league_settings(league)
        season = season or _latest_market_season(db)
        drafted = _drafted_ids(db, league_id, season, drafted_player_ids)
        picks = (
            db.query(LeagueDraftPick)
            .filter(LeagueDraftPick.league_id == league_id, LeagueDraftPick.season == season)
            .order_by(LeagueDraftPick.pick_num.asc())
            .all()
        )
        return _response(
            True,
            data={
                "league_id": league_id,
                "league_name": league.league_name,
                "season": season,
                "settings": {
                    "ppr_type": settings.ppr_type,
                    "num_teams": settings.num_teams,
                    "superflex_slots": settings.superflex_slots,
                    "passing_td_points": settings.passing_td_points,
                },
                "drafted_count": len(drafted),
                "recent_picks": [
                    {
                        "pick": pick.pick_num,
                        "round": pick.round_num,
                        "team": pick.fantasy_team_name,
                        "player": pick.source_player_name,
                        "canonical_player_id": pick.canonical_player_id,
                    }
                    for pick in picks[-10:]
                ],
                "top_available": targets["data"],
            },
            meta={"historical_research_only": True},
        )


def get_bye_week_analysis(
    league_id: int,
    picked_so_far: list[str] | None = None,
    season: int | None = None,
    source: str | None = None,
) -> dict:
    """Analyze bye-week concentration for drafted or selected players."""
    with SessionLocal() as db:
        league = _get_league(db, league_id)
        if league is None:
            return _response(False, error=f"League {league_id} not found")
        season = season or _latest_market_season(db)
        if season is None:
            return _response(False, error="No draft market data imported")

        ids = _drafted_ids(db, league_id, season, picked_so_far)
        rows = []
        for canonical_id in ids:
            query = db.query(DraftPlayerMarket).filter(
                DraftPlayerMarket.season == season,
                DraftPlayerMarket.canonical_player_id == canonical_id,
            )
            if source:
                query = query.filter(DraftPlayerMarket.source == source)
            market = query.first()
            if market:
                rows.append(market)

        by_week: dict[str, list[dict[str, Any]]] = {}
        for market in rows:
            key = str(market.bye_week or "unknown")
            by_week.setdefault(key, []).append(
                {
                    "canonical_player_id": market.canonical_player_id,
                    "player_name": market.source_player_name,
                    "position": market.position,
                    "team": market.team,
                }
            )
        warnings = [
            {"bye_week": week, "count": len(players), "players": players}
            for week, players in by_week.items()
            if week != "unknown" and len(players) >= 3
        ]
        return _response(
            True,
            data={"by_week": by_week, "warnings": warnings},
            meta={"league_id": league_id, "season": season, "historical_research_only": True},
        )
