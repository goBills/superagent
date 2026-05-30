"""Trade Finder v1 — the matching layer for credible 1-for-1 suggestions.

Consumes the deterministic TradeContext payload from `trade_context.get_trade_context`
and finds mutually-beneficial 1-for-1 trades on a drafted league. v1 is brutally
scoped (1-for-1 only) and makes NO projection claim — value is the deterministic
`trade_value_score` (market + scarcity) supplied by the contract.

Seam (locked in the plan):
  * TradeContext supplies `trade_value_score` + `roster_role` (pre-trade snapshot)
    + `eligible_slots`.
  * The matcher recomputes optimal STARTER utility post-swap and gates on mutual
    material improvement — never trusting the pre-trade role after a swap.

Fairness (plan §9C): `lineup_value_delta > 0` for both sides is NECESSARY but not
SUFFICIENT. Anti-fleece (value-gap guardrail) + human-sanity filters (no star-for-
scraps) also apply before a deal is ever surfaced.
"""

from __future__ import annotations

from typing import Any

# Slot fill order MUST mirror trade_context._assign_pre_trade_roles so pre/post-trade
# lineup math is consistent: fixed QB/RB/WR/TE first, then SUPERFLEX, then FLEX.
_FLEX_POSITIONS = {"RB", "WR", "TE"}
_SUPERFLEX_POSITIONS = {"QB", "RB", "WR", "TE"}

# Tunables (v1). Deliberately conservative — we'd rather show 1 great deal than 5 shaky ones.
VALUE_GAP_TOLERANCE = 12.0   # anti-fleece: |give - get| trade_value_score must be within this
MIN_LINEUP_DELTA = 2.0       # both lineups must materially improve, not merely win by rounding dust
STAR_PROTECT_GAP = 18.0      # never give a player worth this much more than what you get back
BALANCE_RATIO_THRESHOLD = 0.5
UPGRADE_VALUE_THRESHOLD = 8.0
DEPTH_ROLES = {"bench", "surplus"}


def _slot_plan(settings: dict[str, Any]) -> dict[str, int]:
    return {
        "QB": int(settings.get("qb_slots") or 0),
        "RB": int(settings.get("rb_slots") or 0),
        "WR": int(settings.get("wr_slots") or 0),
        "TE": int(settings.get("te_slots") or 0),
        "SUPERFLEX": int(settings.get("superflex_slots") or 0),
        "FLEX": int(settings.get("flex_slots") or 0),
    }


def _score(player: dict[str, Any]) -> float:
    return float(player.get("trade_value_score") or 0.0)


def _optimal_lineup_players(players: list[dict[str, Any]], settings: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the optimal starting lineup under the locked slot fill order."""
    slots = _slot_plan(settings)
    remaining = list(players)
    starters: list[dict[str, Any]] = []

    def take(positions: set[str], count: int) -> None:
        nonlocal remaining
        if count <= 0:
            return
        eligible = sorted(
            (p for p in remaining if p.get("position") in positions),
            key=lambda p: (_score(p), -(p.get("effective_rank") or 999.0)),
            reverse=True,
        )
        chosen = eligible[:count]
        chosen_ids = {id(p) for p in chosen}
        starters.extend(chosen)
        remaining = [p for p in remaining if id(p) not in chosen_ids]

    for position in ("QB", "RB", "WR", "TE"):
        take({position}, slots[position])
    take(_SUPERFLEX_POSITIONS, slots["SUPERFLEX"])
    take(_FLEX_POSITIONS, slots["FLEX"])
    return starters


def starter_utility(players: list[dict[str, Any]], settings: dict[str, Any]) -> float:
    """Sum of trade_value_score over the optimal starting lineup.

    Mirrors trade_context._assign_pre_trade_roles fill order (fixed positions →
    SUPERFLEX → FLEX), greedy best-first, which is optimal for this slot structure
    because the flexible slots (supersets) are filled last.
    """
    return round(sum(_score(player) for player in _optimal_lineup_players(players, settings)), 3)


def _swap(players: list[dict[str, Any]], out_id: str, incoming: dict[str, Any]) -> list[dict[str, Any]]:
    """Roster after sending out `out_id` and receiving `incoming`."""
    return [p for p in players if p.get("canonical_player_id") != out_id] + [incoming]


def _team_index(context: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {t["fantasy_team_name"]: t for t in context.get("teams", [])}


def _player_brief(p: dict[str, Any]) -> dict[str, Any]:
    return {
        "canonical_player_id": p.get("canonical_player_id"),
        "player_name": p.get("player_name"),
        "position": p.get("position"),
        "team": p.get("current_team") or p.get("team"),
        "trade_value_score": p.get("trade_value_score"),
        "roster_role": p.get("roster_role"),
        "injury_status": p.get("injury_status"),
        "bye_week": p.get("bye_week"),
        "schedule_context": p.get("schedule_context"),
    }


def _needs(team: dict[str, Any]) -> dict[str, int]:
    return {k: int(v or 0) for k, v in (team.get("needs_by_position") or {}).items()}


def _is_depth(player: dict[str, Any]) -> bool:
    return str(player.get("roster_role") or "").lower() in DEPTH_ROLES


def _has_count_need(needs: dict[str, int], position: str | None) -> bool:
    if not position:
        return False
    if needs.get(position, 0) > 0:
        return True
    return position in _FLEX_POSITIONS and needs.get("FLEX", 0) > 0


def _starter_upgrade_margin(
    players: list[dict[str, Any]],
    settings: dict[str, Any],
    incoming: dict[str, Any],
) -> float | None:
    """Incoming value minus the team's worst current starter at that position.

    FLEX occupants count as starters because `_optimal_lineup_players` returns
    fixed starters plus flexible-slot starters. We only compare against starters
    at the incoming player's own position.
    """
    position = incoming.get("position")
    if not position:
        return None
    same_position_starters = [
        player
        for player in _optimal_lineup_players(players, settings)
        if player.get("position") == position
    ]
    if not same_position_starters:
        return None
    worst_starter = min(_score(player) for player in same_position_starters)
    return round(_score(incoming) - worst_starter, 3)


def _helps_team(
    players: list[dict[str, Any]],
    needs: dict[str, int],
    settings: dict[str, Any],
    incoming: dict[str, Any],
) -> bool:
    if _has_count_need(needs, incoming.get("position")):
        return True
    margin = _starter_upgrade_margin(players, settings, incoming)
    return margin is not None and margin >= UPGRADE_VALUE_THRESHOLD


def _balance_ratio(delta_a: float, delta_b: float) -> float:
    bigger = max(delta_a, delta_b)
    if bigger <= 0:
        return 0.0
    return min(delta_a, delta_b) / bigger


def find_trades(
    context: dict[str, Any],
    my_team_name: str,
    *,
    max_deals: int = 3,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Find up to `max_deals` mutually-beneficial 1-for-1 trades for `my_team_name`.

    Returns {ok, my_team, deals[], provenance, considered, error}. Pure over the
    TradeContext payload — no DB, no projection.
    """
    settings = settings or context.get("settings") or {}
    teams = _team_index(context)
    mine = teams.get(my_team_name)
    if mine is None:
        return {
            "ok": False,
            "error": f"Team '{my_team_name}' not found in this league's draft board.",
            "available_teams": sorted(teams.keys()),
            "deals": [],
        }

    my_players = mine.get("players") or []
    my_base = starter_utility(my_players, settings)
    my_needs = _needs(mine)
    deals: list[dict[str, Any]] = []
    considered = 0

    for opp_name, opp in teams.items():
        if opp_name == my_team_name:
            continue
        opp_players = opp.get("players") or []
        opp_base = starter_utility(opp_players, settings)
        opp_needs = _needs(opp)

        for give in my_players:
            for get in opp_players:
                considered += 1
                gs, rs = _score(give), _score(get)
                # Both managers must be dealing from true depth, not starters/flex core.
                if not _is_depth(give) or not _is_depth(get):
                    continue
                # Complementarity is a hard gate: each incoming player must satisfy
                # a count need or materially upgrade a weak starter.
                if not _helps_team(my_players, my_needs, settings, get):
                    continue
                if not _helps_team(opp_players, opp_needs, settings, give):
                    continue
                # Anti-fleece + star protection guardrails (necessary-not-sufficient gate).
                if abs(gs - rs) > VALUE_GAP_TOLERANCE:
                    continue
                if gs - rs > STAR_PROTECT_GAP:
                    continue
                # Recompute BOTH optimal lineups after the swap (never trust pre-trade role).
                my_after = starter_utility(
                    _swap(my_players, give["canonical_player_id"], get), settings
                )
                opp_after = starter_utility(
                    _swap(opp_players, get["canonical_player_id"], give), settings
                )
                d_mine = round(my_after - my_base, 3)
                d_opp = round(opp_after - opp_base, 3)
                # Mutual improvement is mandatory.
                if d_mine < MIN_LINEUP_DELTA or d_opp < MIN_LINEUP_DELTA:
                    continue
                if _balance_ratio(d_mine, d_opp) < BALANCE_RATIO_THRESHOLD:
                    continue
                mutual_score = round(
                    min(d_mine, d_opp) * 10.0
                    + d_mine
                    + d_opp
                    - abs(d_mine - d_opp) * 0.1,
                    3,
                )
                deals.append({
                    "partner_team": opp_name,
                    "give": _player_brief(give),
                    "get": _player_brief(get),
                    "lineup_value_delta_mine": d_mine,
                    "lineup_value_delta_partner": d_opp,
                    "mutual_benefit_score": mutual_score,
                    "value_gap": round(abs(gs - rs), 3),
                    "why_me": _why(get, give, my_needs, gaining=True),
                    "why_partner": _why(give, get, opp_needs, gaining=True),
                })

    # Rank by mutual acceptability first. A lopsided "I gain 40, they gain 0.4"
    # recommendation may pass raw math, but it is not a compelling trade to send.
    seen: set[tuple] = set()
    ranked: list[dict[str, Any]] = []
    for deal in sorted(
        deals,
        key=lambda d: (
            d["mutual_benefit_score"],
            min(d["lineup_value_delta_mine"], d["lineup_value_delta_partner"]),
            d["lineup_value_delta_mine"] + d["lineup_value_delta_partner"],
            -d["value_gap"],
        ),
        reverse=True,
    ):
        key = (deal["give"]["canonical_player_id"], deal["get"]["canonical_player_id"])
        if key in seen:
            continue
        seen.add(key)
        ranked.append(deal)

    return {
        "ok": True,
        "my_team": my_team_name,
        "deals": ranked[:max_deals],
        "considered": considered,
        "candidates_found": len(deals),
        "provenance": context.get("roster_freshness") or {"label": "Based on draft board"},
        "market_source": context.get("market_source"),
        "error": None,
    }


def _why(incoming: dict[str, Any], outgoing: dict[str, Any], needs: dict[str, int], *, gaining: bool) -> str:
    """Honest, grounded one-liner — no projection language."""
    inc_pos = incoming.get("position")
    out_pos = outgoing.get("position")
    need_hit = needs.get(inc_pos, 0) > 0 or needs.get("FLEX", 0) > 0
    base = f"{incoming.get('player_name')} ({inc_pos}) steps into the starting lineup"
    if need_hit:
        base += f", filling a {inc_pos} need"
    base += f", while {outgoing.get('player_name')} comes from {out_pos} depth."
    return base


def find_trades_for_league(
    league_id: int,
    my_team_name: str = "My Team",
    *,
    max_deals: int = 3,
    season: int | None = None,
    bye_week_season: int | None = None,
    source: str | None = None,
    db: Any = None,
) -> dict[str, Any]:
    """Convenience wrapper: fetch the TradeContext then run the matcher."""
    from superagent.trade_context import get_trade_context

    ctx = get_trade_context(
        league_id=league_id,
        season=season,
        bye_week_season=bye_week_season,
        source=source,
        db=db,
    )
    if not ctx.get("ok"):
        return {"ok": False, "error": ctx.get("error", "Trade context unavailable"), "deals": []}
    return find_trades(ctx["data"], my_team_name, max_deals=max_deals)
