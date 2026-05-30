"""Trade Mode v1 context payloads.

This module builds the deterministic, source-agnostic context that the Trade
Finder matching layer consumes. It intentionally avoids projection claims:
scores are market/scarcity utility, not forecasted points.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from sqlalchemy.orm import Session

from superagent.db import SessionLocal
from superagent.draft_tools import (
    FLEX_ELIGIBLE_POSITIONS,
    _apply_current_context,
    _bye_week_season,
    _current_context_map,
    _draft_sheet_tier,
    _draftable_rank_limit,
    _effective_rank,
    _get_league,
    _latest_market_season,
    _league_settings,
    _market_bye_week,
    _position_need_summary,
)
from superagent.models import DraftPlayerMarket, LeagueDraftPick, LeagueSettings

TRADE_CONTEXT_VERSION = "trade_context.v1"
TRADE_CONTEXT_ROSTER_SOURCE = "draft_board"
DEFAULT_FANTASY_PLAYOFF_WEEKS = [15, 16, 17]


def _response(ok: bool, data: Any = None, error: str | None = None, meta: dict | None = None) -> dict:
    return {"ok": ok, "data": data, "error": error, "meta": meta or {}}


def _settings_payload(settings: LeagueSettings) -> dict[str, Any]:
    return {
        "ppr_type": settings.ppr_type,
        "num_teams": settings.num_teams,
        "roster_spots": settings.roster_spots,
        "qb_slots": settings.qb_slots,
        "rb_slots": settings.rb_slots,
        "wr_slots": settings.wr_slots,
        "te_slots": settings.te_slots,
        "flex_slots": settings.flex_slots,
        "superflex_slots": settings.superflex_slots,
        "bench_spots": settings.bench_spots,
        "taxi_spots": settings.taxi_spots,
        "passing_td_points": settings.passing_td_points,
        "rushing_td_points": settings.rushing_td_points,
        "receiving_td_points": settings.receiving_td_points,
        "pass_yards_per_point": settings.pass_yards_per_point,
        "rush_yards_per_point": settings.rush_yards_per_point,
        "receiving_yards_per_point": settings.receiving_yards_per_point,
    }


def _normalize_position(position: str | None) -> str:
    value = (position or "OTHER").upper()
    if value in {"D/ST", "DEF"}:
        return "DST"
    return value


def _selected_market_rows(
    db: Session,
    season: int,
    source: str | None,
) -> tuple[dict[str, DraftPlayerMarket], list[DraftPlayerMarket]]:
    """Return one preferred market row per canonical player for a season."""
    query = db.query(DraftPlayerMarket).filter(DraftPlayerMarket.season == season)
    if source:
        query = query.filter(DraftPlayerMarket.source == source)

    selected: dict[str, DraftPlayerMarket] = {}
    selected_keys: dict[str, tuple[int, float, int]] = {}
    rows = query.order_by(DraftPlayerMarket.id.asc()).all()
    for market in rows:
        effective_rank, _ = _effective_rank(market)
        source_priority = 0 if market.source == (source or "sleeper_adp") else 1
        key = (
            source_priority,
            float(effective_rank) if effective_rank is not None else float("inf"),
            int(market.id or 0),
        )
        canonical_id = market.canonical_player_id
        if canonical_id not in selected or key < selected_keys[canonical_id]:
            selected[canonical_id] = market
            selected_keys[canonical_id] = key
    return selected, list(selected.values())


def _position_rank_map(markets: list[DraftPlayerMarket]) -> dict[str, int | None]:
    """Compute a fallback position rank when the market source lacks one."""
    by_position: dict[str, list[DraftPlayerMarket]] = defaultdict(list)
    for market in markets:
        by_position[_normalize_position(market.position)].append(market)

    ranks: dict[str, int | None] = {}
    for rows in by_position.values():
        ordered = sorted(
            rows,
            key=lambda market: (
                _effective_rank(market)[0] if _effective_rank(market)[0] is not None else float("inf"),
                market.id or 0,
            ),
        )
        for index, market in enumerate(ordered, start=1):
            ranks[market.canonical_player_id] = market.position_rank or index
    return ranks


def _position_replacement_rank(settings: LeagueSettings, position: str) -> int:
    num_teams = int(settings.num_teams or 12)
    flex_slots = int(settings.flex_slots or 0)
    superflex_slots = int(settings.superflex_slots or 0)
    if position == "QB":
        return max(1, num_teams * (int(settings.qb_slots or 0) + superflex_slots))
    if position == "RB":
        return max(1, round(num_teams * (int(settings.rb_slots or 0) + flex_slots * 0.45)))
    if position == "WR":
        return max(1, round(num_teams * (int(settings.wr_slots or 0) + flex_slots * 0.45)))
    if position == "TE":
        return max(1, round(num_teams * (int(settings.te_slots or 0) + flex_slots * 0.10)))
    if position in {"K", "DST"}:
        return max(1, num_teams)
    return max(1, num_teams)


def _rank_score(effective_rank: float | None, draftable_rank_limit: int) -> float:
    if effective_rank is None:
        return 0.0
    rank = max(1.0, float(effective_rank))
    limit = max(1.0, float(draftable_rank_limit))
    return round(max(0.0, min(100.0, 100.0 * ((limit + 1.0 - rank) / limit))), 3)


def _scarcity_score(position_rank: int | None, replacement_rank: int) -> float:
    if position_rank is None:
        return 0.0
    rank = max(1.0, float(position_rank))
    baseline = max(1.0, float(replacement_rank))
    # 100 near the top of the position; roughly 50 at replacement; fades after.
    return round(max(0.0, min(100.0, 100.0 * ((baseline * 2.0 + 1.0 - rank) / (baseline * 2.0)))), 3)


def _data_quality(payload: dict[str, Any]) -> tuple[str, float]:
    if payload.get("current_context_available") is False:
        return "missing_context", 85.0
    return "complete", 100.0


def _trade_value_components(
    market: DraftPlayerMarket,
    settings: LeagueSettings,
    position_rank: int | None,
    data_quality_score: float,
) -> dict[str, Any]:
    effective_rank, rank_source = _effective_rank(market)
    draftable_rank_limit = _draftable_rank_limit(settings)
    position = _normalize_position(market.position)
    replacement_rank = _position_replacement_rank(settings, position)
    market_rank_score = _rank_score(effective_rank, draftable_rank_limit)
    scarcity_score = _scarcity_score(position_rank, replacement_rank)
    trade_value_score = round(
        (market_rank_score * 0.75) + (scarcity_score * 0.20) + (data_quality_score * 0.05),
        3,
    )
    return {
        "trade_value_score": trade_value_score,
        "market_rank_score": market_rank_score,
        "scarcity_score": scarcity_score,
        "data_quality_score": data_quality_score,
        "effective_rank": effective_rank,
        "rank_source": rank_source,
        "position_rank": position_rank,
        "position_replacement_rank": replacement_rank,
        "weights": {
            "market_rank_score": 0.75,
            "scarcity_score": 0.20,
            "data_quality_score": 0.05,
        },
        "scoring_note": (
            "Deterministic market/scarcity utility from ADP/effective rank, "
            "position scarcity, and data quality. Not a projection."
        ),
    }


def _eligible_slots(position: str, settings: LeagueSettings) -> list[str]:
    slots: list[str] = []
    if position in {"QB", "RB", "WR", "TE", "K", "DST"}:
        slots.append(position)
    if position in FLEX_ELIGIBLE_POSITIONS and int(settings.flex_slots or 0) > 0:
        slots.append("FLEX")
    if position in {"QB", "RB", "WR", "TE"} and int(settings.superflex_slots or 0) > 0:
        slots.append("SUPERFLEX")
    return slots or ["BENCH"]


def _team_freshness(picks: list[LeagueDraftPick]) -> dict[str, Any]:
    as_of = max((pick.created_at for pick in picks if pick.created_at), default=None)
    return {
        "status": "draft_board",
        "label": "Based on draft board",
        "as_of": as_of.isoformat() if as_of else None,
        "pick_count": len(picks),
        "is_stale": False,
    }


def _team_need_fit_for_role(role: str) -> int:
    if role == "starter":
        return 100
    if role == "flex":
        return 85
    if role == "bench":
        return 45
    if role == "surplus":
        return 25
    return 0


def _counts_from_players(players: list[dict[str, Any]]) -> dict[str, int]:
    counts = {position: 0 for position in ["QB", "RB", "WR", "TE"]}
    counts.update({"K": 0, "DST": 0, "OTHER": 0})
    for player in players:
        position = _normalize_position(player.get("position"))
        counts[position if position in counts else "OTHER"] += 1
    return counts


def _assign_pre_trade_roles(players: list[dict[str, Any]], settings: LeagueSettings) -> None:
    """Assign current roster roles from an optimal pre-trade lineup snapshot."""
    remaining = {player["canonical_player_id"] for player in players if player.get("canonical_player_id")}
    by_id = {player["canonical_player_id"]: player for player in players if player.get("canonical_player_id")}

    def eligible_remaining(positions: set[str]) -> list[dict[str, Any]]:
        return sorted(
            [
                player
                for player in players
                if player.get("canonical_player_id") in remaining and player.get("position") in positions
            ],
            key=lambda row: (row.get("trade_value_score") or 0.0, -(row.get("effective_rank") or 999.0)),
            reverse=True,
        )

    fixed_slots = {
        "QB": int(settings.qb_slots or 0),
        "RB": int(settings.rb_slots or 0),
        "WR": int(settings.wr_slots or 0),
        "TE": int(settings.te_slots or 0),
    }
    for position, slot_count in fixed_slots.items():
        for player in eligible_remaining({position})[:slot_count]:
            player["roster_role"] = "starter"
            remaining.discard(player["canonical_player_id"])

    for player in eligible_remaining({"QB", "RB", "WR", "TE"})[: int(settings.superflex_slots or 0)]:
        player["roster_role"] = "flex"
        remaining.discard(player["canonical_player_id"])

    for player in eligible_remaining(set(FLEX_ELIGIBLE_POSITIONS))[: int(settings.flex_slots or 0)]:
        player["roster_role"] = "flex"
        remaining.discard(player["canonical_player_id"])

    position_counts = Counter(player.get("position") for player in players)
    required_by_position = {
        "QB": int(settings.qb_slots or 0) + int(settings.superflex_slots or 0),
        "RB": int(settings.rb_slots or 0),
        "WR": int(settings.wr_slots or 0),
        "TE": int(settings.te_slots or 0),
    }
    for canonical_id in list(remaining):
        player = by_id[canonical_id]
        position = player.get("position")
        if position in FLEX_ELIGIBLE_POSITIONS and position_counts[position] > required_by_position.get(position, 0):
            player["roster_role"] = "surplus"
        elif position in required_by_position and position_counts[position] > required_by_position.get(position, 0):
            player["roster_role"] = "surplus"
        else:
            player["roster_role"] = "bench"

    for player in players:
        player.setdefault("roster_role", "bench")
        player["team_need_fit"] = _team_need_fit_for_role(player["roster_role"])
        player["team_fit_delta"] = player["team_need_fit"] - 50
        player["value_components"]["roster_role"] = player["roster_role"]
        player["value_components"]["team_need_fit"] = player["team_need_fit"]


def _player_flags(row: dict[str, Any], team_bye_counts: Counter) -> list[str]:
    flags: list[str] = []
    if row.get("injury_status"):
        flags.append("injury")
    if row.get("current_team_differs"):
        flags.append("team_changed")
    if row.get("current_context_available") is False:
        flags.append("current_context_missing")
    bye_week = row.get("bye_week")
    if bye_week is not None and team_bye_counts.get(bye_week, 0) >= 2:
        flags.append("bye_cluster")
    return flags


def _schedule_context_payload(
    *,
    bye_week: int | None,
    bye_source: str | None,
    bye_week_season: int | None,
) -> dict[str, Any]:
    """Small, honest forward-looking schedule facts for Trade Mode.

    This is intentionally not a projection surface. Bye weeks are real schedule
    facts; strength-of-schedule is left unavailable until we have a defensible
    opponent-strength source for the requested season.
    """
    playoff_weeks = list(DEFAULT_FANTASY_PLAYOFF_WEEKS)
    return {
        "source": "schedule",
        "bye_week": bye_week,
        "bye_week_source": bye_source,
        "bye_week_season": bye_week_season,
        "playoff_weeks": playoff_weeks,
        "playoff_weeks_source": "default_fantasy_playoffs",
        "playoff_weeks_bye": bool(bye_week in playoff_weeks) if bye_week is not None else False,
        "sos_tier": None,
        "sos_source": None,
        "sos_note": (
            "Strength of schedule is not computed in this payload yet; "
            "do not present it as a projection."
        ),
    }


def _build_player_payload(
    market: DraftPlayerMarket,
    settings: LeagueSettings,
    bye_week_season: int,
    position_rank: int | None,
    context_map: dict[str, Any],
) -> dict[str, Any]:
    effective_rank, rank_source = _effective_rank(market)
    bye_week, bye_source, resolved_bye_week_season = _market_bye_week(market, bye_week_season)
    position = _normalize_position(market.position)
    payload: dict[str, Any] = {
        "canonical_player_id": market.canonical_player_id,
        "player_name": market.source_player_name,
        "position": position,
        "team": market.team,
        "bye_week": bye_week,
        "bye_week_source": bye_source,
        "bye_week_season": resolved_bye_week_season,
        "schedule_context": _schedule_context_payload(
            bye_week=bye_week,
            bye_source=bye_source,
            bye_week_season=resolved_bye_week_season,
        ),
        "adp": market.adp,
        "effective_rank": effective_rank,
        "rank_source": rank_source,
        "position_rank": position_rank,
        "tier": _draft_sheet_tier(effective_rank).get("tier"),
        "tier_level": _draft_sheet_tier(effective_rank).get("tier_level"),
        "eligible_slots": _eligible_slots(position, settings),
    }
    _apply_current_context(payload, context_map.get(market.canonical_player_id))
    data_quality, data_quality_score = _data_quality(payload)
    components = _trade_value_components(market, settings, position_rank, data_quality_score)
    payload["trade_value_score"] = components["trade_value_score"]
    payload["value_components"] = components
    payload["data_quality"] = data_quality
    return payload


def _build_context(
    db: Session,
    league_id: int,
    season: int | None,
    bye_week_season: int | None,
    source: str | None,
) -> dict:
    league = _get_league(db, league_id)
    if league is None:
        return _response(False, error=f"League {league_id} not found")
    season = season or _latest_market_season(db)
    if season is None:
        return _response(False, error="No draft market data imported")
    bye_week_season = _bye_week_season(season, bye_week_season)
    settings = _league_settings(league)
    markets_by_id, selected_markets = _selected_market_rows(db, season, source)
    position_ranks = _position_rank_map(selected_markets)

    picks = (
        db.query(LeagueDraftPick)
        .filter(LeagueDraftPick.league_id == league_id, LeagueDraftPick.season == season)
        .order_by(LeagueDraftPick.pick_num.asc(), LeagueDraftPick.id.asc())
        .all()
    )
    context_map = _current_context_map(db, [pick.canonical_player_id for pick in picks])

    teams: dict[str, dict[str, Any]] = {}
    unresolved_players: list[dict[str, Any]] = []
    for pick in picks:
        team_name = (pick.fantasy_team_name or "Unknown Team").strip() or "Unknown Team"
        team = teams.setdefault(
            team_name,
            {
                "fantasy_team_name": team_name,
                "pick_count": 0,
                "counts_by_position": {},
                "needs_by_position": {},
                "surplus_by_position": {},
                "players": [],
            },
        )
        team["pick_count"] += 1
        if not pick.canonical_player_id:
            unresolved_players.append(
                {
                    "fantasy_team_name": team_name,
                    "pick_num": pick.pick_num,
                    "player_name": pick.source_player_name,
                    "reason": "Unresolved canonical player",
                }
            )
            continue
        market = markets_by_id.get(pick.canonical_player_id)
        if market is None:
            unresolved_players.append(
                {
                    "fantasy_team_name": team_name,
                    "pick_num": pick.pick_num,
                    "player_name": pick.source_player_name,
                    "canonical_player_id": pick.canonical_player_id,
                    "reason": "No draft market row for selected source/season",
                }
            )
            continue
        team["players"].append(
            _build_player_payload(
                market=market,
                settings=settings,
                bye_week_season=bye_week_season,
                position_rank=position_ranks.get(market.canonical_player_id),
                context_map=context_map,
            )
        )

    for team in teams.values():
        counts = _counts_from_players(team["players"])
        needs_summary = _position_need_summary(settings, counts)
        team["counts_by_position"] = counts
        team["needs_by_position"] = {
            **needs_summary["base_needs"],
            "FLEX": needs_summary["flex_depth_needed"],
        }
        _assign_pre_trade_roles(team["players"], settings)
        team["surplus_by_position"] = dict(
            Counter(player["position"] for player in team["players"] if player.get("roster_role") == "surplus")
        )
        bye_counts = Counter(player.get("bye_week") for player in team["players"] if player.get("bye_week") is not None)
        for player in team["players"]:
            player["flags"] = _player_flags(player, bye_counts)
        team["players"].sort(
            key=lambda player: (
                player.get("trade_value_score") or 0.0,
                -(player.get("effective_rank") or 999.0),
            ),
            reverse=True,
        )

    source_values = sorted({market.source for market in selected_markets})
    data = {
        "contract_version": TRADE_CONTEXT_VERSION,
        "league_id": league_id,
        "league_name": league.league_name,
        "season": season,
        "market_source": source or ("mixed" if len(source_values) != 1 else source_values[0]),
        "market_sources": source_values,
        "roster_source": TRADE_CONTEXT_ROSTER_SOURCE,
        "roster_freshness": _team_freshness(picks),
        "settings": _settings_payload(settings),
        "teams": sorted(teams.values(), key=lambda row: row["fantasy_team_name"].lower()),
        "unresolved_players": unresolved_players,
        "semantics": {
            "trade_value_score": (
                "0-100 deterministic market/scarcity utility. It is transferable asset value, "
                "not a projection and not discounted by current bench/surplus role."
            ),
            "roster_role": "Pre-trade snapshot only; recompute roles after any candidate swap.",
            "lineup_value_delta": (
                "Computed by the matching layer by refilling each team's optimal starters with "
                "trade_value_score after a candidate swap."
            ),
            "schedule_context": (
                "Forward-looking schedule facts only. Bye/playoff-bye flags are schedule facts; "
                "strength-of-schedule is null until a defensible source is attached. Not a projection."
            ),
        },
    }
    return _response(
        True,
        data=data,
        meta={
            "league_id": league_id,
            "season": season,
            "market_source": data["market_source"],
            "contract_version": TRADE_CONTEXT_VERSION,
        },
    )


def get_trade_context(
    league_id: int,
    season: int | None = None,
    bye_week_season: int | None = None,
    source: str | None = None,
    db: Session | None = None,
) -> dict:
    """Return the v1 TradeContext payload for a drafted league."""
    if db is not None:
        return _build_context(db, league_id, season, bye_week_season, source)
    with SessionLocal() as session:
        return _build_context(session, league_id, season, bye_week_season, source)
