"""Tests for the Trade Finder matching engine (trade_finder.py)."""

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from superagent.trade_finder import (  # noqa: E402
    BALANCE_RATIO_THRESHOLD,
    DEPTH_ROLES,
    MIN_LINEUP_DELTA,
    UPGRADE_VALUE_THRESHOLD,
    VALUE_GAP_TOLERANCE,
    find_trades,
    starter_utility,
)

# 1 QB / 2 RB / 2 WR / 1 TE / 1 FLEX, no superflex.
SETTINGS = {
    "qb_slots": 1, "rb_slots": 2, "wr_slots": 2, "te_slots": 1,
    "flex_slots": 1, "superflex_slots": 0,
}


def _p(pid, name, pos, score, rank=100.0, role="bench"):
    slots = [pos]
    if pos in {"RB", "WR", "TE"}:
        slots.append("FLEX")
    return {
        "canonical_player_id": pid, "player_name": name, "position": pos,
        "trade_value_score": score, "effective_rank": rank, "eligible_slots": slots,
        "roster_role": role, "current_team": "XX", "bye_week": 9, "injury_status": None,
    }


# Team A: deep at RB (RB4 is a true bench asset), weak at WR2.
TEAM_A = {
    "fantasy_team_name": "My Team",
    "needs_by_position": {"QB": 0, "RB": 0, "WR": 1, "TE": 0, "FLEX": 0},
    "surplus_by_position": {"RB": 1},
    "players": [
        _p("a_qb", "A QB", "QB", 80, role="starter"),
        _p("a_rb1", "A RB1", "RB", 92, role="starter"),
        _p("a_rb2", "A RB2", "RB", 90, role="starter"),
        _p("a_rb3", "A RB3", "RB", 86, role="flex"),
        _p("a_rb4", "A RB4", "RB", 78, role="surplus"),  # true depth
        _p("a_wr1", "A WR1", "WR", 70, role="starter"),
        _p("a_wr2", "A WR2", "WR", 35, role="starter"),  # weak starter
        _p("a_te", "A TE", "TE", 65, role="starter"),
    ],
}

# Team B: deep at WR (WR4 bench), weak at RB2.
TEAM_B = {
    "fantasy_team_name": "Team Salam",
    "needs_by_position": {"QB": 0, "RB": 1, "WR": 0, "TE": 0, "FLEX": 0},
    "surplus_by_position": {"WR": 1},
    "players": [
        _p("b_qb", "B QB", "QB", 78, role="starter"),
        _p("b_wr1", "B WR1", "WR", 94, role="starter"),
        _p("b_wr2", "B WR2", "WR", 91, role="starter"),
        _p("b_wr3", "B WR3", "WR", 80, role="flex"),
        _p("b_wr4", "B WR4", "WR", 76, role="surplus"),  # true depth
        _p("b_rb1", "B RB1", "RB", 68, role="starter"),
        _p("b_rb2", "B RB2", "RB", 33, role="starter"),  # weak starter
        _p("b_te", "B TE", "TE", 62, role="starter"),
    ],
}

CONTEXT = {
    "settings": SETTINGS,
    "teams": [TEAM_A, TEAM_B],
    "roster_freshness": {"label": "Based on draft board"},
    "market_source": "sleeper_adp",
}


def test_starter_utility_optimal_lineup():
    # A's optimal starters: QB80, RB92, RB90, WR70, WR35, TE65, FLEX=RB3 86 (RB4 78 benched).
    assert starter_utility(TEAM_A["players"], SETTINGS) == 518.0
    # B's: QB78, RB68, RB33, WR94, WR91, TE62, FLEX=WR3 80 (WR4 76 benched).
    assert starter_utility(TEAM_B["players"], SETTINGS) == 506.0


def test_finds_mutually_beneficial_swap():
    result = find_trades(CONTEXT, "My Team", max_deals=3)
    assert result["ok"] is True
    assert result["deals"], "expected at least one mutually-beneficial deal"
    top = result["deals"][0]
    # The complementary win-win direction: I deal from RB depth to fix my WR need.
    # (Exact players are whatever maximizes my lineup gain — the engine finds the optimum,
    # which may be a stronger deal than a human eyeballs; assert the shape, not a fixed pair.)
    assert top["give"]["position"] == "RB"
    assert top["get"]["position"] == "WR"
    assert top["partner_team"] == "Team Salam"
    assert top["lineup_value_delta_mine"] >= MIN_LINEUP_DELTA
    assert top["lineup_value_delta_partner"] >= MIN_LINEUP_DELTA
    # Top deal should be ranked by mutual acceptability, not only my biggest gain.
    assert top["mutual_benefit_score"] == max(d["mutual_benefit_score"] for d in result["deals"])


def test_no_deal_breaches_anti_fleece_or_hurts_either_side():
    result = find_trades(CONTEXT, "My Team", max_deals=10)
    for deal in result["deals"]:
        assert deal["value_gap"] <= VALUE_GAP_TOLERANCE          # anti-fleece
        assert deal["lineup_value_delta_mine"] >= MIN_LINEUP_DELTA       # I materially improve
        assert deal["lineup_value_delta_partner"] >= MIN_LINEUP_DELTA    # they materially improve
        ratio = min(deal["lineup_value_delta_mine"], deal["lineup_value_delta_partner"]) / max(
            deal["lineup_value_delta_mine"], deal["lineup_value_delta_partner"]
        )
        assert ratio >= BALANCE_RATIO_THRESHOLD
        assert deal["give"]["roster_role"] in DEPTH_ROLES
        assert deal["get"]["roster_role"] in DEPTH_ROLES


def test_requires_partner_need_or_upgrade_for_my_give():
    context = copy.deepcopy(CONTEXT)
    partner = context["teams"][1]
    partner["needs_by_position"] = {"QB": 0, "RB": 0, "WR": 0, "TE": 0, "FLEX": 0}
    for player in partner["players"]:
        if player["canonical_player_id"] == "b_rb2":
            player["trade_value_score"] = 88
    result = find_trades(context, "My Team", max_deals=10)
    assert result["ok"] is True
    assert result["deals"] == []


def test_need_or_upgrade_allows_deep_roster_upgrade_without_count_need():
    team_a = {
        "fantasy_team_name": "My Team",
        "needs_by_position": {"QB": 0, "RB": 0, "WR": 0, "TE": 0, "FLEX": 0},
        "surplus_by_position": {"RB": 1},
        "players": [
            _p("ua_qb", "UA QB", "QB", 80, role="starter"),
            _p("ua_rb1", "UA RB1", "RB", 90, role="starter"),
            _p("ua_rb2", "UA RB2", "RB", 88, role="starter"),
            _p("ua_rb3", "UA RB3", "RB", 78, role="flex"),
            _p("ua_rb4", "UA RB4", "RB", 76, role="surplus"),
            _p("ua_wr1", "UA WR1", "WR", 82, role="starter"),
            _p("ua_wr2", "UA WR2", "WR", 75, role="starter"),
            _p("ua_te", "UA TE", "TE", 65, role="starter"),
        ],
    }
    team_b = {
        "fantasy_team_name": "Team Upgrade",
        "needs_by_position": {"QB": 0, "RB": 0, "WR": 0, "TE": 0, "FLEX": 0},
        "surplus_by_position": {"WR": 1},
        "players": [
            _p("ub_qb", "UB QB", "QB", 78, role="starter"),
            _p("ub_rb1", "UB RB1", "RB", 85, role="starter"),
            _p("ub_rb2", "UB RB2", "RB", 68, role="starter"),
            _p("ub_wr1", "UB WR1", "WR", 95, role="starter"),
            _p("ub_wr2", "UB WR2", "WR", 90, role="starter"),
            _p("ub_wr3", "UB WR3", "WR", 86, role="flex"),
            _p("ub_wr4", "UB WR4", "WR", 84, role="surplus"),
            _p("ub_te", "UB TE", "TE", 64, role="starter"),
        ],
    }
    result = find_trades(
        {
            "settings": SETTINGS,
            "teams": [team_a, team_b],
            "roster_freshness": {"label": "Based on draft board"},
        },
        "My Team",
    )
    assert result["deals"], f"expected upgrade threshold {UPGRADE_VALUE_THRESHOLD} to allow a deal"
    top = result["deals"][0]
    assert top["give"]["player_name"] == "UA RB4"
    assert top["get"]["player_name"] == "UB WR4"


def test_unknown_team_returns_error_not_crash():
    result = find_trades(CONTEXT, "Nonexistent Team")
    assert result["ok"] is False
    assert "Team Salam" in result["available_teams"]
    assert result["deals"] == []


def test_provenance_passed_through():
    result = find_trades(CONTEXT, "My Team")
    assert result["provenance"]["label"] == "Based on draft board"
