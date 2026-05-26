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
from superagent.models import DraftPlayerMarket, League, LeagueDraftPick, LeagueRosterPlayer, LeagueSettings
from superagent.official_bye_weeks import (
    OFFICIAL_BYE_WEEK_SOURCE,
    latest_official_bye_week_season,
    official_bye_week_for_team,
)

ELITE_DST_EFFECTIVE_RANK_CUTOFF = 140
DEFAULT_DRAFTABLE_RANK_LIMIT = 240
CORE_ROSTER_POSITIONS = ["QB", "RB", "WR", "TE"]
FLEX_ELIGIBLE_POSITIONS = {"RB", "WR", "TE"}


def _response(ok: bool, data: Any = None, error: str | None = None, meta: dict | None = None) -> dict:
    return {"ok": ok, "data": data, "error": error, "meta": meta or {}}


def _get_league(db: Session, league_id: int) -> League | None:
    return db.query(League).filter(League.id == league_id).first()


def _league_settings(league: League) -> LeagueSettings:
    return league.settings or LeagueSettings(league_id=league.id)


def _latest_market_season(db: Session) -> int | None:
    row = db.query(DraftPlayerMarket.season).order_by(DraftPlayerMarket.season.desc()).first()
    return int(row[0]) if row else None


def _bye_week_season(market_season: int, requested_bye_week_season: int | None = None) -> int:
    if requested_bye_week_season is not None:
        return requested_bye_week_season
    official_season = latest_official_bye_week_season()
    if official_season is not None and market_season <= official_season:
        return official_season
    return market_season


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


def _stored_roster_names(
    db: Session,
    league_id: int,
    season: int,
    fantasy_team_name: str | None = None,
) -> list[str]:
    query = db.query(LeagueRosterPlayer).filter(
        LeagueRosterPlayer.league_id == league_id,
        LeagueRosterPlayer.season == season,
    )
    if fantasy_team_name:
        query = query.filter(LeagueRosterPlayer.fantasy_team_name == fantasy_team_name)
    return [row.source_player_name for row in query.all()]


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


def _market_for_name(
    db: Session,
    name: str,
    season: int,
    source: str | None = None,
) -> tuple[DraftPlayerMarket | None, dict[str, Any] | None]:
    resolution = resolve_to_canonical(name, season, db=db)
    query = db.query(DraftPlayerMarket).filter(DraftPlayerMarket.season == season)
    if source:
        query = query.filter(DraftPlayerMarket.source == source)
    if resolution["ok"]:
        query = query.filter(DraftPlayerMarket.canonical_player_id == resolution["canonical_player_id"])
    else:
        query = query.filter(DraftPlayerMarket.source_player_name == name)
    return query.first(), resolution


def _roster_markets(
    db: Session,
    roster_names: list[str],
    season: int,
    source: str | None = None,
) -> tuple[list[DraftPlayerMarket], list[dict[str, Any]]]:
    rows = []
    unresolved = []
    seen_ids = set()
    for name in roster_names:
        market, resolution = _market_for_name(db, name, season, source=source)
        if market is None:
            unresolved.append(
                {
                    "player_name": name,
                    "reason": resolution.get("error") if resolution else "No draft market row found",
                }
            )
            continue
        if market.canonical_player_id in seen_ids:
            continue
        seen_ids.add(market.canonical_player_id)
        rows.append(market)
    return rows, unresolved


def _canonical_ids_for_markets(markets: list[DraftPlayerMarket]) -> list[str]:
    return [market.canonical_player_id for market in markets if market.canonical_player_id]


def _effective_rank(market: DraftPlayerMarket) -> tuple[float | None, str | None]:
    if market.adp is not None:
        return market.adp, "ADP"
    if market.avg_rank is not None:
        return market.avg_rank, "avg rank"
    if market.overall_rank is not None:
        return market.overall_rank, "overall rank"
    return None, None


def _draftable_rank_limit(settings: LeagueSettings) -> int:
    num_teams = settings.num_teams or 12
    roster_spots = settings.roster_spots or 16
    return max(1, min(int(num_teams * roster_spots), 350))


def _starter_requirements(settings: LeagueSettings) -> dict[str, int]:
    return {
        "QB": int(settings.qb_slots or 0) + int(settings.superflex_slots or 0),
        "RB": int(settings.rb_slots or 0),
        "WR": int(settings.wr_slots or 0),
        "TE": int(settings.te_slots or 0),
        "FLEX": int(settings.flex_slots or 0),
    }


def _roster_counts(markets: list[DraftPlayerMarket]) -> dict[str, int]:
    counts = {position: 0 for position in CORE_ROSTER_POSITIONS}
    counts.update({"K": 0, "DST": 0, "OTHER": 0})
    for market in markets:
        position = (market.position or "OTHER").upper()
        if position in {"D/ST", "DEF"}:
            position = "DST"
        counts[position if position in counts else "OTHER"] += 1
    return counts


def _market_bye_week(market: DraftPlayerMarket, bye_week_season: int | None = None) -> tuple[int | None, str, int | None]:
    if bye_week_season is not None and market.team:
        official_bye = official_bye_week_for_team(bye_week_season, market.team)
        if official_bye is not None:
            return official_bye, OFFICIAL_BYE_WEEK_SOURCE, bye_week_season
    return market.bye_week, "draft_market", market.season


def _bye_week_groups(
    markets: list[DraftPlayerMarket],
    bye_week_season: int | None = None,
) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for market in markets:
        bye_week, bye_source, resolved_bye_week_season = _market_bye_week(market, bye_week_season)
        week = str(bye_week or "unknown")
        groups.setdefault(week, []).append(
            {
                "canonical_player_id": market.canonical_player_id,
                "player_name": market.source_player_name,
                "position": market.position,
                "team": market.team,
                "bye_week_source": bye_source,
                "bye_week_season": resolved_bye_week_season,
            }
        )
    return groups


def _position_need_summary(settings: LeagueSettings, counts: dict[str, int], picks_remaining: int | None = None) -> dict:
    requirements = _starter_requirements(settings)
    base_needs = {
        position: max(0, requirements[position] - counts.get(position, 0))
        for position in CORE_ROSTER_POSITIONS
    }
    flex_eligible_count = sum(counts.get(position, 0) for position in FLEX_ELIGIBLE_POSITIONS)
    required_flex_pool = requirements["RB"] + requirements["WR"] + requirements["TE"] + requirements["FLEX"]
    flex_depth_needed = max(0, required_flex_pool - flex_eligible_count)
    priority_order = []
    for position in ["RB", "WR", "QB", "TE"]:
        if base_needs.get(position, 0) > 0:
            priority_order.append(position)
    if flex_depth_needed > sum(base_needs.values()):
        for position in ["RB", "WR", "TE"]:
            if position not in priority_order:
                priority_order.append(position)
    if not priority_order:
        priority_order = ["RB", "WR", "QB", "TE"]
    return {
        "requirements": requirements,
        "counts": counts,
        "base_needs": base_needs,
        "flex_eligible_count": flex_eligible_count,
        "required_flex_pool": required_flex_pool,
        "flex_depth_needed": flex_depth_needed,
        "priority_positions": priority_order,
        "picks_remaining": picks_remaining,
    }


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


def _market_payload(
    market: DraftPlayerMarket,
    settings: LeagueSettings,
    bye_week_season: int | None = None,
) -> dict[str, Any]:
    adjusted = adjust_draft_value(market, settings)
    effective_rank, rank_source = _effective_rank(market)
    bye_week, bye_source, resolved_bye_week_season = _market_bye_week(market, bye_week_season)
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
        "bye_week": bye_week,
        "bye_week_source": bye_source,
        "bye_week_season": resolved_bye_week_season,
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
    drafted_player_ids: list[str] | None = None,
    season: int | None = None,
    bye_week_season: int | None = None,
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
        bye_week_season = _bye_week_season(season, bye_week_season)
        settings = _league_settings(league)
        draftable_rank_limit = _draftable_rank_limit(settings)
        applied_max_effective_rank = max_effective_rank
        if applied_max_effective_rank is None and not _is_explicit_special_teams_request(position):
            applied_max_effective_rank = draftable_rank_limit
        drafted = _drafted_ids(db, league_id, season, drafted_player_ids)
        rows = []
        for market in _market_rows(db, season, source=source, position=position):
            if market.canonical_player_id in drafted:
                continue
            effective_rank, _ = _effective_rank(market)
            if min_effective_rank is not None and (effective_rank is None or effective_rank < min_effective_rank):
                continue
            if applied_max_effective_rank is not None and (
                effective_rank is None or effective_rank > applied_max_effective_rank
            ):
                continue
            market_bye_week, _, _ = _market_bye_week(market, bye_week_season)
            if bye_week_filters and market_bye_week in set(bye_week_filters):
                continue
            payload = _market_payload(market, settings, bye_week_season=bye_week_season)
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
                "market_season": season,
                "bye_week_season": bye_week_season,
                "bye_week_source": (
                    OFFICIAL_BYE_WEEK_SOURCE if bye_week_season == latest_official_bye_week_season() else "draft_market"
                ),
                "source": source,
                "position": position,
                "min_effective_rank": min_effective_rank,
                "max_effective_rank": max_effective_rank,
                "applied_max_effective_rank": applied_max_effective_rank,
                "draftable_rank_limit": draftable_rank_limit,
                "min_adp": min_adp,
                "max_adp": max_adp,
                "rank_semantics": (
                    "Effective Rank uses ADP when available, otherwise avg rank, otherwise overall rank. "
                    "Default results are capped at the league's draftable roster range unless a max rank is provided."
                ),
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
    bye_week_season: int | None = None,
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
        bye_week_season = _bye_week_season(season, bye_week_season)
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
            payload = _market_payload(market, settings, bye_week_season=bye_week_season)
            payload["ok"] = True
            rows.append(payload)
        rows.sort(key=lambda row: row.get("adjusted_value", -999), reverse=True)
        return _response(
            True,
            data=rows,
            meta={
                "league_id": league_id,
                "season": season,
                "market_season": season,
                "bye_week_season": bye_week_season,
                "historical_research_only": True,
            },
        )


def get_draft_context(
    league_id: int,
    drafted_player_ids: list[str] | None = None,
    season: int | None = None,
    bye_week_season: int | None = None,
    source: str | None = None,
) -> dict:
    """Summarize league settings, draft progress, and top available values."""
    targets = find_draft_targets(
        league_id=league_id,
        season=season,
        bye_week_season=bye_week_season,
        source=source,
        limit=10,
    )
    if not targets["ok"]:
        return targets
    with SessionLocal() as db:
        league = _get_league(db, league_id)
        settings = _league_settings(league)
        season = season or _latest_market_season(db)
        bye_week_season = _bye_week_season(season, bye_week_season)
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
                "market_season": season,
                "bye_week_season": bye_week_season,
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
    bye_week_season: int | None = None,
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
        bye_week_season = _bye_week_season(season, bye_week_season)

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
            bye_week, bye_source, resolved_bye_week_season = _market_bye_week(market, bye_week_season)
            key = str(bye_week or "unknown")
            by_week.setdefault(key, []).append(
                {
                    "canonical_player_id": market.canonical_player_id,
                    "player_name": market.source_player_name,
                    "position": market.position,
                    "team": market.team,
                    "bye_week_source": bye_source,
                    "bye_week_season": resolved_bye_week_season,
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
            meta={
                "league_id": league_id,
                "season": season,
                "market_season": season,
                "bye_week_season": bye_week_season,
                "historical_research_only": True,
            },
        )


def check_bye_week_conflicts(
    league_id: int,
    current_roster: list[str] | None = None,
    fantasy_team_name: str | None = None,
    threshold: int = 3,
    season: int | None = None,
    bye_week_season: int | None = None,
    source: str | None = None,
) -> dict:
    """Check bye-week concentration for a user's current draft roster."""
    with SessionLocal() as db:
        league = _get_league(db, league_id)
        if league is None:
            return _response(False, error=f"League {league_id} not found")
        season = season or _latest_market_season(db)
        if season is None:
            return _response(False, error="No draft market data imported")
        bye_week_season = _bye_week_season(season, bye_week_season)
        roster_names = current_roster or _stored_roster_names(db, league_id, season, fantasy_team_name)
        markets, unresolved = _roster_markets(db, roster_names, season, source=source)
        by_week = _bye_week_groups(markets, bye_week_season=bye_week_season)
        threshold = max(2, threshold)
        warnings = [
            {"bye_week": week, "count": len(players), "players": players}
            for week, players in by_week.items()
            if week != "unknown" and len(players) >= threshold
        ]
        return _response(
            True,
            data={"by_week": by_week, "warnings": warnings, "unresolved": unresolved},
            meta={
                "league_id": league_id,
                "season": season,
                "market_season": season,
                "bye_week_season": bye_week_season,
                "threshold": threshold,
                "historical_research_only": True,
            },
        )


def get_position_needs(
    league_id: int,
    current_roster: list[str] | None = None,
    fantasy_team_name: str | None = None,
    picks_remaining: int | None = None,
    season: int | None = None,
    bye_week_season: int | None = None,
    source: str | None = None,
) -> dict:
    """Summarize roster position needs using league settings and current drafted players."""
    with SessionLocal() as db:
        league = _get_league(db, league_id)
        if league is None:
            return _response(False, error=f"League {league_id} not found")
        season = season or _latest_market_season(db)
        if season is None:
            return _response(False, error="No draft market data imported")
        bye_week_season = _bye_week_season(season, bye_week_season)
        settings = _league_settings(league)
        roster_names = current_roster or _stored_roster_names(db, league_id, season, fantasy_team_name)
        markets, unresolved = _roster_markets(db, roster_names, season, source=source)
        counts = _roster_counts(markets)
        summary = _position_need_summary(settings, counts, picks_remaining=picks_remaining)
        summary["roster"] = [
            _market_payload(market, settings, bye_week_season=bye_week_season)
            for market in markets
        ]
        summary["unresolved"] = unresolved
        return _response(
            True,
            data=summary,
            meta={
                "league_id": league_id,
                "season": season,
                "market_season": season,
                "bye_week_season": bye_week_season,
                "historical_research_only": True,
            },
        )


def get_roster_construction_context(
    league_id: int,
    current_roster: list[str] | None = None,
    fantasy_team_name: str | None = None,
    picks_remaining: int | None = None,
    season: int | None = None,
    bye_week_season: int | None = None,
    source: str | None = None,
) -> dict:
    """Return roster construction context: counts, needs, byes, and top values."""
    needs = get_position_needs(
        league_id=league_id,
        current_roster=current_roster,
        fantasy_team_name=fantasy_team_name,
        picks_remaining=picks_remaining,
        season=season,
        bye_week_season=bye_week_season,
        source=source,
    )
    if not needs["ok"]:
        return needs
    bye = check_bye_week_conflicts(
        league_id=league_id,
        current_roster=current_roster,
        fantasy_team_name=fantasy_team_name,
        season=needs["meta"]["season"],
        bye_week_season=needs["meta"].get("bye_week_season"),
        source=source,
    )
    drafted_ids = [row["canonical_player_id"] for row in needs["data"]["roster"] if row.get("canonical_player_id")]
    targets_by_position = {}
    for position in needs["data"]["priority_positions"][:4]:
        targets = find_draft_targets(
            league_id=league_id,
            position=position,
            drafted_player_ids=drafted_ids,
            season=needs["meta"]["season"],
            source=source,
            bye_week_season=needs["meta"].get("bye_week_season"),
            limit=5,
        )
        targets_by_position[position] = targets["data"] if targets["ok"] else []
    return _response(
        True,
        data={
            "position_needs": needs["data"],
            "bye_week_analysis": bye["data"] if bye["ok"] else {"by_week": {}, "warnings": []},
            "targets_by_position": targets_by_position,
        },
        meta={
            "league_id": league_id,
            "season": needs["meta"]["season"],
            "market_season": needs["meta"]["season"],
            "bye_week_season": needs["meta"].get("bye_week_season"),
            "historical_research_only": True,
        },
    )


def recommend_next_pick_targets(
    league_id: int,
    current_roster: list[str] | None = None,
    fantasy_team_name: str | None = None,
    current_pick: float | None = None,
    picks_remaining: int | None = None,
    season: int | None = None,
    bye_week_season: int | None = None,
    source: str | None = None,
    limit: int = 12,
) -> dict:
    """Recommend next-pick target pools based on roster needs and market value."""
    context = get_roster_construction_context(
        league_id=league_id,
        current_roster=current_roster,
        fantasy_team_name=fantasy_team_name,
        picks_remaining=picks_remaining,
        season=season,
        bye_week_season=bye_week_season,
        source=source,
    )
    if not context["ok"]:
        return context
    season = context["meta"]["season"]
    needs = context["data"]["position_needs"]
    drafted_ids = [row["canonical_player_id"] for row in needs["roster"] if row.get("canonical_player_id")]
    min_rank = current_pick
    recommendations = []
    for position in needs["priority_positions"][:4]:
        targets = find_draft_targets(
            league_id=league_id,
            position=position,
            min_effective_rank=min_rank,
            drafted_player_ids=drafted_ids,
            season=season,
            bye_week_season=context["meta"].get("bye_week_season"),
            source=source,
            limit=max(3, min(limit, 20)),
        )
        if not targets["ok"]:
            continue
        need_bonus = 0
        if needs["base_needs"].get(position, 0) > 0:
            need_bonus += 8
        elif position in FLEX_ELIGIBLE_POSITIONS and needs["flex_depth_needed"] > 0:
            need_bonus += 4
        for row in targets["data"][:5]:
            rec = dict(row)
            rec["need_bonus"] = need_bonus
            rec["recommendation_score"] = round((row.get("value_delta") or 0) + (row.get("adjusted_value") or 0) + need_bonus, 3)
            rec["roster_fit"] = "starter need" if need_bonus >= 8 else "flex/depth need" if need_bonus else "value depth"
            recommendations.append(rec)
    recommendations.sort(key=lambda row: row["recommendation_score"], reverse=True)
    limit = max(1, min(limit, 50))
    return _response(
        True,
        data={
            "recommendations": recommendations[:limit],
            "position_needs": needs,
            "bye_week_warnings": context["data"]["bye_week_analysis"].get("warnings", []),
        },
        meta={
            "league_id": league_id,
            "season": season,
            "market_season": season,
            "bye_week_season": context["meta"].get("bye_week_season"),
            "current_pick": current_pick,
            "rank_window_note": "When current_pick is supplied, targets use Effective Rank at or after that pick and within the league draftable range.",
            "historical_research_only": True,
        },
    )
