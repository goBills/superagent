"""
Tests for Trade Mode v1 context payloads.
"""

import sys
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from superagent.api import app  # noqa: E402
from superagent.canonical_resolution import normalize_player_name  # noqa: E402
from superagent.db import SessionLocal  # noqa: E402
from superagent.models import (  # noqa: E402
    CanonicalPlayer,
    CanonicalPlayerAlias,
    DraftMarketImport,
    DraftPlayerMarket,
    League,
    LeagueDraftPick,
    LeagueSettings,
    PlayerCurrentContext,
    User,
)
from superagent.trade_context import get_trade_context  # noqa: E402

client = TestClient(app)


def _add_player(db, import_batch, source, season, suffix, key, name, position, team, adp, position_rank):
    canonical_id = f"trade_{key}_{suffix}"
    db.add(
        CanonicalPlayer(
            canonical_player_id=canonical_id,
            nflverse_player_id=canonical_id,
            full_name=name,
            normalized_name=normalize_player_name(name),
        )
    )
    db.flush()
    db.add(
        CanonicalPlayerAlias(
            canonical_player_id=canonical_id,
            alias=name,
            normalized_alias=normalize_player_name(name),
            source="trade-context-test",
        )
    )
    db.add(
        DraftPlayerMarket(
            import_id=import_batch.id,
            source=source,
            season=season,
            canonical_player_id=canonical_id,
            source_player_name=name,
            team=team,
            position=position,
            position_rank=position_rank,
            bye_week=7,
            adp=adp,
            value=50,
        )
    )
    return canonical_id


def _setup_trade_context_fixture():
    email = f"trade-context-{uuid.uuid4().hex}@example.com"
    register = client.post("/auth/register", json={"email": email, "password": "password123"})
    assert register.status_code == 200, register.text
    headers = {"Authorization": f"Bearer {register.json()['token']}"}

    suffix = uuid.uuid4().hex[:10]
    season = 2031
    source = f"trade-context-{suffix}"
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).first()
        league = League(user_id=user.id, league_name="Trade Context League", league_type="snake")
        db.add(league)
        db.flush()
        db.add(
            LeagueSettings(
                league_id=league.id,
                ppr_type="ppr",
                num_teams=2,
                roster_spots=5,
                qb_slots=1,
                rb_slots=1,
                wr_slots=1,
                te_slots=0,
                flex_slots=1,
                superflex_slots=0,
                bench_spots=2,
            )
        )
        import_batch = DraftMarketImport(
            source=source,
            season=season,
            file_name=f"{source}.csv",
            rows_seen=8,
            rows_imported=8,
        )
        db.add(import_batch)
        db.flush()
        players = {
            "a_qb": _add_player(db, import_batch, source, season, suffix, "a_qb", f"Atlas QB {suffix}", "QB", "BUF", 8, 1),
            "a_rb1": _add_player(db, import_batch, source, season, suffix, "a_rb1", f"Atlas RB One {suffix}", "RB", "DET", 10, 1),
            "a_rb2": _add_player(db, import_batch, source, season, suffix, "a_rb2", f"Atlas RB Two {suffix}", "RB", "DET", 32, 2),
            "a_rb3": _add_player(db, import_batch, source, season, suffix, "a_rb3", f"Atlas RB Three {suffix}", "RB", "DET", 88, 6),
            "b_qb": _add_player(db, import_batch, source, season, suffix, "b_qb", f"Beacon QB {suffix}", "QB", "DAL", 12, 2),
            "b_wr1": _add_player(db, import_batch, source, season, suffix, "b_wr1", f"Beacon WR One {suffix}", "WR", "CIN", 11, 1),
            "b_wr2": _add_player(db, import_batch, source, season, suffix, "b_wr2", f"Beacon WR Two {suffix}", "WR", "CIN", 36, 2),
            "b_wr3": _add_player(db, import_batch, source, season, suffix, "b_wr3", f"Beacon WR Three {suffix}", "WR", "CIN", 92, 6),
        }
        db.add(
            PlayerCurrentContext(
                canonical_player_id=players["a_rb1"],
                season=season,
                source="sleeper",
                source_player_id=f"sleeper_{players['a_rb1']}",
                full_name=f"Atlas RB One {suffix}",
                normalized_name=normalize_player_name(f"Atlas RB One {suffix}"),
                position="RB",
                team="DET",
                age=24,
                years_exp=3,
                status="Active",
            )
        )
        db.flush()
        picks = [
            (1, "Atlas", "a_qb"),
            (2, "Beacon", "b_qb"),
            (3, "Atlas", "a_rb1"),
            (4, "Beacon", "b_wr1"),
            (5, "Atlas", "a_rb2"),
            (6, "Beacon", "b_wr2"),
            (7, "Atlas", "a_rb3"),
            (8, "Beacon", "b_wr3"),
        ]
        for pick_num, team_name, key in picks:
            db.add(
                LeagueDraftPick(
                    league_id=league.id,
                    season=season,
                    round_num=((pick_num - 1) // 2) + 1,
                    pick_num=pick_num,
                    fantasy_team_name=team_name,
                    source_player_name=db.query(DraftPlayerMarket)
                    .filter(DraftPlayerMarket.canonical_player_id == players[key])
                    .first()
                    .source_player_name,
                    position=db.query(DraftPlayerMarket)
                    .filter(DraftPlayerMarket.canonical_player_id == players[key])
                    .first()
                    .position,
                    canonical_player_id=players[key],
                    mapping_status="mapped",
                )
            )
        db.add(
            LeagueDraftPick(
                league_id=league.id,
                season=season,
                round_num=5,
                pick_num=9,
                fantasy_team_name="Atlas",
                source_player_name=f"Unknown Flex {suffix}",
                position=None,
                canonical_player_id=None,
                mapping_status="needs_review",
            )
        )
        db.commit()
        return headers, league.id, season, source


def test_trade_context_reconstructs_teams_and_exposes_explainable_values():
    _, league_id, season, source = _setup_trade_context_fixture()

    result = get_trade_context(league_id=league_id, season=season, source=source)

    assert result["ok"] is True, result
    data = result["data"]
    assert data["contract_version"] == "trade_context.v1"
    assert data["roster_source"] == "draft_board"
    assert data["roster_freshness"]["label"] == "Based on draft board"
    assert data["market_source"] == source
    assert "stock_score" not in data["teams"][0]["players"][0]

    teams = {team["fantasy_team_name"]: team for team in data["teams"]}
    assert set(teams) == {"Atlas", "Beacon"}
    assert teams["Atlas"]["pick_count"] == 5
    assert teams["Atlas"]["counts_by_position"]["RB"] == 3
    assert teams["Atlas"]["needs_by_position"]["WR"] == 1
    assert teams["Atlas"]["surplus_by_position"]["RB"] == 1

    atlas_players = {player["player_name"]: player for player in teams["Atlas"]["players"]}
    surplus_rb = next(player for player in atlas_players.values() if player["roster_role"] == "surplus")
    assert surplus_rb["position"] == "RB"
    assert surplus_rb["team_need_fit"] == 25
    assert surplus_rb["trade_value_score"] > 0
    assert surplus_rb["eligible_slots"] == ["RB", "FLEX"]
    assert surplus_rb["schedule_context"] == {
        "source": "schedule",
        "bye_week": 7,
        "bye_week_source": "draft_market",
        "bye_week_season": season,
        "playoff_weeks": [15, 16, 17],
        "playoff_weeks_source": "default_fantasy_playoffs",
        "playoff_weeks_bye": False,
        "sos_tier": None,
        "sos_source": None,
        "sos_note": (
            "Strength of schedule is not computed in this payload yet; "
            "do not present it as a projection."
        ),
    }
    assert "market_rank_score" in surplus_rb["value_components"]
    assert surplus_rb["value_components"]["scarcity_score"] > 0
    assert surplus_rb["value_components"]["roster_role"] == "surplus"
    assert "Not a projection" in surplus_rb["value_components"]["scoring_note"]

    complete_player = next(player for player in atlas_players.values() if player["data_quality"] == "complete")
    assert complete_player["value_components"]["market_rank_score"] > 0
    assert complete_player["age"] == 24
    assert complete_player["current_team"] == "DET"
    assert "current_context_missing" not in complete_player["flags"]
    assert data["unresolved_players"][0]["reason"] == "Unresolved canonical player"
    assert "lineup_value_delta" in data["semantics"]
    assert "Not a projection" in data["semantics"]["schedule_context"]


def test_trade_context_endpoint_is_authenticated_and_league_scoped():
    headers, league_id, season, source = _setup_trade_context_fixture()

    response = client.get(
        f"/leagues/{league_id}/trade/context?season={season}&source={source}",
        headers=headers,
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["contract_version"] == "trade_context.v1"
    assert len(data["teams"]) == 2

    other = client.post(
        "/auth/register",
        json={"email": f"trade-context-other-{uuid.uuid4().hex}@example.com", "password": "password123"},
    )
    other_headers = {"Authorization": f"Bearer {other.json()['token']}"}
    forbidden = client.get(
        f"/leagues/{league_id}/trade/context?season={season}&source={source}",
        headers=other_headers,
    )
    assert forbidden.status_code == 404
