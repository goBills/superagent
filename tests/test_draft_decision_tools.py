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
    check_bye_week_conflicts,
    compare_draft_options,
    find_draft_targets,
    get_bye_week_analysis,
    get_draft_context,
    get_position_needs,
    get_roster_construction_context,
    recommend_next_pick_targets,
    get_available_targets,
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


def setup_draft_fixture(season=2029):
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


def test_get_available_targets_excludes_recorded_draft_board():
    league_id, season, source = setup_draft_fixture()

    result = get_available_targets(league_id=league_id, season=season, source=source, limit=10)

    assert result["ok"] is True
    assert "Josh Allen" not in [row["player_name"] for row in result["data"]]


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


def test_find_draft_targets_uses_2026_official_byes_with_older_market_data():
    league_id, season, source = setup_draft_fixture(season=2025)

    result = find_draft_targets(
        league_id=league_id,
        season=season,
        source=source,
        position="QB",
        min_effective_rank=20,
        max_effective_rank=40,
    )

    assert result["ok"] is True
    by_name = {row["player_name"]: row for row in result["data"]}
    assert by_name["Lamar Jackson"]["bye_week"] == 13
    assert by_name["Lamar Jackson"]["bye_week_source"] == "nfl.com"
    assert by_name["Lamar Jackson"]["bye_week_season"] == 2026
    assert result["meta"]["market_season"] == 2025
    assert result["meta"]["bye_week_season"] == 2026


def test_check_bye_week_conflicts_uses_2026_official_byes_with_older_market_data():
    league_id, season, source = setup_draft_fixture(season=2025)

    result = check_bye_week_conflicts(
        league_id=league_id,
        season=season,
        source=source,
        current_roster=["Josh Allen", "James Cook", "Khalil Shakir"],
    )

    assert result["ok"] is True
    assert result["data"]["warnings"][0]["bye_week"] == "7"
    assert result["data"]["warnings"][0]["players"][0]["bye_week_source"] == "nfl.com"
    assert result["meta"]["market_season"] == 2025
    assert result["meta"]["bye_week_season"] == 2026


def test_find_draft_targets_supports_after_pick_language_with_min_adp():
    league_id, season, source = setup_draft_fixture()

    result = find_draft_targets(
        league_id=league_id,
        season=season,
        source=source,
        position="RB",
        min_adp=50,
    )

    assert result["ok"] is True
    assert [row["player_name"] for row in result["data"]] == ["James Cook"]
    assert result["meta"]["min_adp"] == 50
    assert result["meta"]["min_effective_rank"] == 50
    assert result["data"][0]["effective_rank"] == 55
    assert result["data"][0]["rank_source"] == "ADP"
    assert result["data"][0]["draft_position"] == 55
    assert result["data"][0]["draft_position_source"] == "ADP"


def test_find_draft_targets_supports_min_effective_rank_name():
    league_id, season, source = setup_draft_fixture()

    result = find_draft_targets(
        league_id=league_id,
        season=season,
        source=source,
        position="RB",
        min_effective_rank=50,
    )

    assert result["ok"] is True
    assert [row["player_name"] for row in result["data"]] == ["James Cook"]
    assert result["meta"]["min_effective_rank"] == 50
    assert result["meta"]["min_adp"] is None


def test_find_draft_targets_uses_avg_rank_when_adp_missing():
    league_id, season, source = setup_draft_fixture()
    with SessionLocal() as db:
        market = (
            db.query(DraftPlayerMarket)
            .filter(
                DraftPlayerMarket.source == source,
                DraftPlayerMarket.source_player_name == "James Cook",
            )
            .first()
        )
        market.adp = None
        market.avg_rank = 75
        db.commit()

    result = find_draft_targets(
        league_id=league_id,
        season=season,
        source=source,
        position="RB",
        min_adp=70,
    )

    assert result["ok"] is True
    assert [row["player_name"] for row in result["data"]] == ["James Cook"]
    assert result["data"][0]["adp"] is None
    assert result["data"][0]["effective_rank"] == 75
    assert result["data"][0]["rank_source"] == "avg rank"
    assert result["data"][0]["draft_position"] == 75
    assert result["data"][0]["draft_position_source"] == "avg rank"


def test_find_draft_targets_caps_after_pick_results_to_draftable_range():
    league_id, season, source = setup_draft_fixture()
    with SessionLocal() as db:
        import_batch = db.query(DraftMarketImport).filter(DraftMarketImport.source == source).first()
        add_player(db, "nfl_deep_rb_tools", "Deep Bench RB", "NYG", "RB", season)
        db.add(
            DraftPlayerMarket(
                import_id=import_batch.id,
                source=source,
                season=season,
                canonical_player_id="nfl_deep_rb_tools",
                source_player_name="Deep Bench RB",
                position="RB",
                team="NYG",
                avg_rank=310,
                ecr=150,
                value=30,
            )
        )
        db.commit()

    result = find_draft_targets(
        league_id=league_id,
        season=season,
        source=source,
        position="RB",
        min_effective_rank=50,
    )

    assert result["ok"] is True
    assert "Deep Bench RB" not in [row["player_name"] for row in result["data"]]
    assert result["meta"]["draftable_rank_limit"] == 192
    assert result["meta"]["applied_max_effective_rank"] == 192


def test_find_draft_targets_excludes_k_and_non_elite_dst_by_default():
    league_id, season, source = setup_draft_fixture()
    with SessionLocal() as db:
        import_batch = db.query(DraftMarketImport).filter(DraftMarketImport.source == source).first()
        add_player(db, "nfl_justin_tucker_tools", "Justin Tucker", "BAL", "K", season)
        add_player(db, "nfl_miami_dst_tools", "Miami Dolphins", "MIA", "DST", season)
        db.add_all(
            [
                DraftPlayerMarket(
                    import_id=import_batch.id,
                    source=source,
                    season=season,
                    canonical_player_id="nfl_justin_tucker_tools",
                    source_player_name="Justin Tucker",
                    position="K",
                    team="BAL",
                    adp=125,
                    ecr=100,
                    value=30,
                ),
                DraftPlayerMarket(
                    import_id=import_batch.id,
                    source=source,
                    season=season,
                    canonical_player_id="nfl_miami_dst_tools",
                    source_player_name="Miami Dolphins",
                    position="DST",
                    team="MIA",
                    adp=187,
                    ecr=150,
                    value=30,
                ),
            ]
        )
        db.commit()

    result = find_draft_targets(league_id=league_id, season=season, source=source, limit=20)

    names = [row["player_name"] for row in result["data"]]
    assert "Justin Tucker" not in names
    assert "Miami Dolphins" not in names


def test_find_draft_targets_includes_elite_dst_by_default():
    league_id, season, source = setup_draft_fixture()
    with SessionLocal() as db:
        import_batch = db.query(DraftMarketImport).filter(DraftMarketImport.source == source).first()
        add_player(db, "nfl_baltimore_dst_tools", "Baltimore Ravens", "BAL", "DST", season)
        db.add(
            DraftPlayerMarket(
                import_id=import_batch.id,
                source=source,
                season=season,
                canonical_player_id="nfl_baltimore_dst_tools",
                source_player_name="Baltimore Ravens",
                position="DST",
                team="BAL",
                adp=135,
                ecr=120,
                value=30,
            )
        )
        db.commit()

    result = find_draft_targets(league_id=league_id, season=season, source=source, limit=20)

    names = [row["player_name"] for row in result["data"]]
    assert "Baltimore Ravens" in names


def test_find_draft_targets_includes_dst_when_explicitly_requested():
    league_id, season, source = setup_draft_fixture()
    with SessionLocal() as db:
        import_batch = db.query(DraftMarketImport).filter(DraftMarketImport.source == source).first()
        add_player(db, "nfl_miami_dst_explicit_tools", "Miami Dolphins", "MIA", "DST", season)
        db.add(
            DraftPlayerMarket(
                import_id=import_batch.id,
                source=source,
                season=season,
                canonical_player_id="nfl_miami_dst_explicit_tools",
                source_player_name="Miami Dolphins",
                position="DST",
                team="MIA",
                adp=187,
                ecr=150,
                value=30,
            )
        )
        db.commit()

    result = find_draft_targets(league_id=league_id, season=season, source=source, position="DST", limit=20)

    assert [row["player_name"] for row in result["data"]] == ["Miami Dolphins"]


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


def test_check_bye_week_conflicts_uses_current_roster_names():
    league_id, season, source = setup_draft_fixture()

    result = check_bye_week_conflicts(
        league_id=league_id,
        season=season,
        source=source,
        current_roster=["Josh Allen", "James Cook", "Khalil Shakir"],
    )

    assert result["ok"] is True
    assert result["data"]["warnings"][0]["bye_week"] == "7"
    assert result["data"]["warnings"][0]["count"] == 3


def test_get_position_needs_identifies_missing_starters():
    league_id, season, source = setup_draft_fixture()

    result = get_position_needs(
        league_id=league_id,
        season=season,
        source=source,
        current_roster=["Josh Allen", "James Cook"],
        picks_remaining=14,
    )

    assert result["ok"] is True
    assert result["data"]["counts"]["QB"] == 1
    assert result["data"]["counts"]["RB"] == 1
    assert result["data"]["base_needs"]["WR"] == 2
    assert result["data"]["base_needs"]["TE"] == 1
    assert "WR" in result["data"]["priority_positions"]


def test_get_roster_construction_context_returns_targets_by_needed_position():
    league_id, season, source = setup_draft_fixture()

    result = get_roster_construction_context(
        league_id=league_id,
        season=season,
        source=source,
        current_roster=["Josh Allen", "James Cook"],
    )

    assert result["ok"] is True
    assert "position_needs" in result["data"]
    assert "bye_week_analysis" in result["data"]
    assert "targets_by_position" in result["data"]
    assert "WR" in result["data"]["targets_by_position"]


def test_recommend_next_pick_targets_scores_roster_fit():
    league_id, season, source = setup_draft_fixture()

    result = recommend_next_pick_targets(
        league_id=league_id,
        season=season,
        source=source,
        current_roster=["Josh Allen", "James Cook"],
        current_pick=20,
        limit=5,
    )

    assert result["ok"] is True
    assert result["data"]["recommendations"]
    assert result["data"]["recommendations"][0]["roster_fit"] in {
        "starter need",
        "flex/depth need",
        "value depth",
    }
    assert "position_needs" in result["data"]


def test_recommend_next_pick_prioritizes_best_available_over_sleepers():
    """At an early pick, the best player available (lowest effective rank) must
    rank above undervalued late-round sleepers, even when sleepers have a much
    larger value delta. Regression for the pick-3 'Cedric Tillman' bug."""
    league_id, season, source = setup_draft_fixture()
    with SessionLocal() as db:
        import_batch = db.query(DraftMarketImport).filter(DraftMarketImport.source == source).first()
        # Elite WR at rank 4 with a near-zero value delta.
        add_player(db, "nfl_elite_wr_tools", "Elite WR", "DET", "WR", season)
        # Late-round sleeper at rank 203 with a huge positive value delta.
        add_player(db, "nfl_sleeper_wr_tools", "Sleeper WR", "CLE", "WR", season)
        db.add_all(
            [
                DraftPlayerMarket(
                    import_id=import_batch.id,
                    source=source,
                    season=season,
                    canonical_player_id="nfl_elite_wr_tools",
                    source_player_name="Elite WR",
                    position="WR",
                    team="DET",
                    adp=4,
                    ecr=4,
                    value=95,
                ),
                DraftPlayerMarket(
                    import_id=import_batch.id,
                    source=source,
                    season=season,
                    canonical_player_id="nfl_sleeper_wr_tools",
                    source_player_name="Sleeper WR",
                    position="WR",
                    team="CLE",
                    adp=22,  # within the next-pick window at pick 3
                    ecr=5,  # large +17 value delta, the bug's trap
                    value=20,
                ),
            ]
        )
        db.commit()

    result = recommend_next_pick_targets(
        league_id=league_id,
        season=season,
        source=source,
        current_roster=[],
        current_pick=3,
        limit=10,
    )

    assert result["ok"] is True
    wr_recs = [r for r in result["data"]["recommendations"] if r["position"] == "WR"]
    assert wr_recs, "expected WR recommendations"
    elite_idx = next(i for i, r in enumerate(wr_recs) if r["player_name"] == "Elite WR")
    sleeper_idx = next(i for i, r in enumerate(wr_recs) if r["player_name"] == "Sleeper WR")
    assert elite_idx < sleeper_idx, "best player available must outrank the sleeper"


def test_recommend_next_pick_surfaces_fallen_elite_ranked_better_than_pick():
    """An elite player who falls and is still available must surface even when
    ranked better than the current pick. Regression for the lower-bound bug where
    min_effective_rank=current_pick filtered out e.g. a rank-1 player at pick 3."""
    league_id, season, source = setup_draft_fixture()
    with SessionLocal() as db:
        import_batch = db.query(DraftMarketImport).filter(DraftMarketImport.source == source).first()
        # Rank-1 RB that is NOT drafted (still on the board) while we sit at pick 3.
        add_player(db, "nfl_fallen_elite_rb_tools", "Fallen Elite RB", "SF", "RB", season)
        db.add(
            DraftPlayerMarket(
                import_id=import_batch.id,
                source=source,
                season=season,
                canonical_player_id="nfl_fallen_elite_rb_tools",
                source_player_name="Fallen Elite RB",
                position="RB",
                team="SF",
                adp=1,
                ecr=1,
                value=99,
            )
        )
        db.commit()

    result = recommend_next_pick_targets(
        league_id=league_id,
        season=season,
        source=source,
        current_roster=[],
        current_pick=3,
        limit=10,
    )

    assert result["ok"] is True
    names = [r["player_name"] for r in result["data"]["recommendations"]]
    assert "Fallen Elite RB" in names, "rank-1 faller still available must be recommended at pick 3"
    # And it should lead the board, being the best player available.
    assert result["data"]["recommendations"][0]["player_name"] == "Fallen Elite RB"


def test_find_draft_targets_sort_by_rank_orders_by_effective_rank():
    """sort_by='rank' returns best player available first (lowest effective rank)."""
    league_id, season, source = setup_draft_fixture()

    result = find_draft_targets(
        league_id=league_id, season=season, source=source, sort_by="rank", limit=10
    )

    assert result["ok"] is True
    assert result["meta"]["sort_by"] == "rank"
    ranks = [row["effective_rank"] for row in result["data"] if row["effective_rank"] is not None]
    assert ranks == sorted(ranks), "results should be ordered by ascending effective rank"


def test_find_draft_targets_excludes_unresolved_pick_by_name():
    """A recorded pick that failed canonical resolution (needs_review, no canonical
    id) must still be excluded from targets by name. Regression for bulk paste
    leaking unresolved players back into the available pool."""
    league_id, season, source = setup_draft_fixture()
    with SessionLocal() as db:
        db.add(
            LeagueDraftPick(
                league_id=league_id,
                season=season,
                round_num=1,
                pick_num=2,
                fantasy_team_name="Other",
                source_player_name="Khalil Shakir",  # matches a market player by name
                position="WR",
                canonical_player_id=None,  # resolution failed -> not caught by id exclusion
                mapping_status="needs_review",
            )
        )
        db.commit()

    result = find_draft_targets(league_id=league_id, season=season, source=source, limit=20)
    assert result["ok"] is True
    names = [row["player_name"] for row in result["data"]]
    assert "Khalil Shakir" not in names


def test_draft_decision_tools_registered_for_agent():
    names = {schema["name"] for schema in TOOL_SCHEMAS}

    for name in [
        "find_draft_targets",
        "get_available_targets",
        "compare_draft_options",
        "get_draft_context",
        "get_bye_week_analysis",
        "check_bye_week_conflicts",
        "get_position_needs",
        "get_roster_construction_context",
        "recommend_next_pick_targets",
    ]:
        assert name in TOOL_DISPATCH
        assert name in names
