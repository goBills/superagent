"""
Tests for Phase 10D draft decision tools.
"""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from superagent.canonical_resolution import normalize_player_name  # noqa: E402
from superagent.db import SessionLocal  # noqa: E402
from superagent.draft_tools import (  # noqa: E402
    compare_draft_options,
    find_draft_targets,
    get_bye_week_analysis,
    get_draft_context,
)
from superagent.models import (  # noqa: E402
    CanonicalPlayer,
    CanonicalPlayerAlias,
    DraftMarketImport,
    DraftPlayerMarket,
    League,
    LeagueDraftPick,
    LeagueSettings,
    PlayerSeason,
    User,
)
from superagent.tool_schemas import TOOL_DISPATCH, TOOL_SCHEMAS  # noqa: E402


def add_player(db, player_id, name, team, position, season):
    existing = db.query(CanonicalPlayer).filter(CanonicalPlayer.canonical_player_id == player_id).first()
    if existing is None:
        db.add(
            CanonicalPlayer(
                canonical_player_id=player_id,
                nflverse_player_id=player_id,
                full_name=name,
                normalized_name=normalize_player_name(name),
            )
        )
        db.flush()
    if not db.query(PlayerSeason).filter(
        PlayerSeason.canonical_player_id == player_id,
        PlayerSeason.season == season,
        PlayerSeason.team == team,
        PlayerSeason.position == position,
    ).first():
        db.add(PlayerSeason(canonical_player_id=player_id, season=season, team=team, position=position))
    if not db.query(CanonicalPlayerAlias).filter(
        CanonicalPlayerAlias.canonical_player_id == player_id,
        CanonicalPlayerAlias.normalized_alias == normalize_player_name(name),
        CanonicalPlayerAlias.source == "draft-tools-test",
    ).first():
        db.add(
            CanonicalPlayerAlias(
                canonical_player_id=player_id,
                alias=name,
                normalized_alias=normalize_player_name(name),
                source="draft-tools-test",
            )
        )


def setup_draft_fixture():
    season = 2029
    source = f"draft-test-{uuid.uuid4().hex}"
    with SessionLocal() as db:
        user = User(email=f"draft-{uuid.uuid4().hex}@example.com", password_hash="hash")
        db.add(user)
        db.flush()
        league = League(user_id=user.id, league_name="Draft Tools League", league_type="snake")
        db.add(league)
        db.flush()
        db.add(
            LeagueSettings(
                league_id=league.id,
                ppr_type="ppr",
                num_teams=12,
                superflex_slots=1,
                passing_td_points=6,
            )
        )
        add_player(db, "nfl_josh_allen_tools", "Josh Allen", "BUF", "QB", season)
        add_player(db, "nfl_james_cook_tools", "James Cook", "BUF", "RB", season)
        add_player(db, "nfl_khalil_shakir_tools", "Khalil Shakir", "BUF", "WR", season)
        add_player(db, "nfl_lamar_jackson_tools", "Lamar Jackson", "BAL", "QB", season)
        import_batch = DraftMarketImport(
            source=source,
            season=season,
            file_name=f"{source}.csv",
            rows_seen=4,
            rows_imported=4,
        )
        db.add(import_batch)
        db.flush()
        rows = [
            ("nfl_josh_allen_tools", "Josh Allen", "QB", "BUF", 7, 24, 20, 40),
            ("nfl_james_cook_tools", "James Cook", "RB", "BUF", 7, 55, 45, 28),
            ("nfl_khalil_shakir_tools", "Khalil Shakir", "WR", "BUF", 7, 110, 88, 18),
            ("nfl_lamar_jackson_tools", "Lamar Jackson", "QB", "BAL", 10, 28, 22, 38),
        ]
        for canonical_id, name, position, team, bye, adp, ecr, value in rows:
            db.add(
                DraftPlayerMarket(
                    import_id=import_batch.id,
                    source=source,
                    season=season,
                    canonical_player_id=canonical_id,
                    source_player_name=name,
                    position=position,
                    team=team,
                    bye_week=bye,
                    adp=adp,
                    ecr=ecr,
                    value=value,
                )
            )
        db.add(
            LeagueDraftPick(
                league_id=league.id,
                season=season,
                round_num=1,
                pick_num=1,
                fantasy_team_name="Rob",
                source_player_name="Josh Allen",
                position="QB",
                canonical_player_id="nfl_josh_allen_tools",
                mapping_status="mapped",
            )
        )
        db.commit()
        return league.id, season, source


def test_find_draft_targets_excludes_drafted_and_sorts_value():
    league_id, season, source = setup_draft_fixture()

    result = find_draft_targets(league_id=league_id, season=season, source=source, limit=3)

    assert result["ok"] is True
    names = [row["player_name"] for row in result["data"]]
    assert "Josh Allen" not in names
    assert names[0] == "Lamar Jackson"


def test_find_draft_targets_filters_position_adp_and_bye():
    league_id, season, source = setup_draft_fixture()

    result = find_draft_targets(
        league_id=league_id,
        season=season,
        source=source,
        position="WR",
        max_adp=120,
        bye_week_filters=[10],
    )

    assert result["ok"] is True
    assert [row["player_name"] for row in result["data"]] == ["Khalil Shakir"]


def test_compare_draft_options_uses_league_adjustments():
    league_id, season, source = setup_draft_fixture()

    result = compare_draft_options(
        league_id=league_id,
        season=season,
        source=source,
        player_names=["James Cook", "Lamar Jackson"],
    )

    assert result["ok"] is True
    assert result["data"][0]["player_name"] == "Lamar Jackson"
    assert result["data"][0]["league_adjustment"] > result["data"][1]["league_adjustment"]


def test_get_draft_context_returns_settings_and_top_available():
    league_id, season, source = setup_draft_fixture()

    result = get_draft_context(league_id=league_id, season=season, source=source)

    assert result["ok"] is True
    assert result["data"]["settings"]["superflex_slots"] == 1
    assert result["data"]["drafted_count"] == 1
    assert result["data"]["top_available"]


def test_get_bye_week_analysis_warns_on_concentration():
    league_id, season, source = setup_draft_fixture()

    result = get_bye_week_analysis(
        league_id=league_id,
        season=season,
        source=source,
        picked_so_far=["nfl_james_cook_tools", "nfl_khalil_shakir_tools"],
    )

    assert result["ok"] is True
    assert result["data"]["warnings"][0]["bye_week"] == "7"
    assert result["data"]["warnings"][0]["count"] == 3


def test_draft_decision_tools_registered_for_agent():
    names = {schema["name"] for schema in TOOL_SCHEMAS}

    for name in [
        "find_draft_targets",
        "compare_draft_options",
        "get_draft_context",
        "get_bye_week_analysis",
    ]:
        assert name in TOOL_DISPATCH
        assert name in names
