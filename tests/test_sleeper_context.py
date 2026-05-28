"""Tests for Sleeper current-context refresh."""

import duckdb
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from superagent.canonical_resolution import canonical_id_from_nflverse, normalize_player_name
from superagent.data.refresh_sleeper_context import refresh_sleeper_context
from superagent.db import SessionLocal, init_db
from superagent.models import (
    CanonicalPlayer,
    DraftMarketImport,
    DraftPlayerMarket,
    ExternalPlayerMapping,
    PlayerCurrentContext,
    PlayerSeason,
)


init_db()


def make_crosswalk_db(tmp_path, rows):
    """Create a tiny DuckDB rosters table for crosswalk tests."""
    path = tmp_path / f"crosswalk-{uuid.uuid4().hex}.duckdb"
    conn = duckdb.connect(str(path))
    conn.execute(
        """
        CREATE TABLE rosters (
            season INTEGER,
            sleeper_id VARCHAR,
            gsis_id VARCHAR,
            full_name VARCHAR
        )
        """
    )
    for row in rows:
        conn.execute("INSERT INTO rosters VALUES (?, ?, ?, ?)", row)
    conn.close()
    return str(path)


def add_canonical(db, player_id: str, full_name: str, position: str = "WR", team: str = "TB", season: int = 2025):
    canonical_id = canonical_id_from_nflverse(player_id, full_name)
    db.add(
        CanonicalPlayer(
            canonical_player_id=canonical_id,
            nflverse_player_id=player_id,
            full_name=full_name,
            normalized_name=normalize_player_name(full_name),
        )
    )
    db.add(PlayerSeason(canonical_player_id=canonical_id, season=season, team=team, position=position))
    db.commit()
    return canonical_id


def test_refresh_sleeper_context_maps_by_roster_crosswalk_and_updates_team(tmp_path):
    player_id = f"gsis-{uuid.uuid4().hex}"
    sleeper_id = f"slp-{uuid.uuid4().hex}"
    duckdb_path = make_crosswalk_db(tmp_path, [(2025, sleeper_id, player_id, "Mike Evans")])
    with SessionLocal() as db:
        canonical_id = add_canonical(db, player_id, "Mike Evans", team="TB")
        summary = refresh_sleeper_context(
            season=2026,
            db=db,
            duckdb_path=duckdb_path,
            players={
                sleeper_id: {
                    "player_id": sleeper_id,
                    "full_name": "Mike Evans",
                    "position": "WR",
                    "team": "SF",
                    "age": 33,
                    "years_exp": 12,
                    "injury_status": None,
                    "depth_chart_position": "WR",
                }
            },
        )

        context = db.query(PlayerCurrentContext).filter(PlayerCurrentContext.source_player_id == sleeper_id).one()
        mapping = db.query(ExternalPlayerMapping).filter(ExternalPlayerMapping.source_player_id == sleeper_id).one()

    assert summary["mapped_by_crosswalk"] == 1
    assert summary["team_changes_vs_latest_season"] == 1
    assert context.canonical_player_id == canonical_id
    assert context.team == "SF"
    assert context.years_exp == 12
    assert context.injury_status is None
    assert mapping.status == "approved"
    assert mapping.confidence == 1.0


def test_refresh_sleeper_context_maps_draftable_player_from_market_row(tmp_path):
    sleeper_id = f"slp-{uuid.uuid4().hex}"
    player_name = f"Rookie Runner {uuid.uuid4().hex[:8]}"
    source = f"draft-{uuid.uuid4().hex}"
    duckdb_path = make_crosswalk_db(tmp_path, [])
    with SessionLocal() as db:
        canonical_id = add_canonical(db, f"gsis-{uuid.uuid4().hex}", player_name, position="RB", team="BUF")
        import_batch = DraftMarketImport(source=source, season=2026, file_name="draft.csv", rows_seen=1, rows_imported=1)
        db.add(import_batch)
        db.flush()
        market = DraftPlayerMarket(
            import_id=import_batch.id,
            source=source,
            season=2026,
            canonical_player_id=canonical_id,
            source_player_name=player_name,
            position="RB",
            team="BUF",
            avg_rank=88,
        )
        db.add(market)
        db.commit()

        summary = refresh_sleeper_context(
            season=2026,
            db=db,
            duckdb_path=duckdb_path,
            players={
                sleeper_id: {
                    "player_id": sleeper_id,
                    "full_name": player_name,
                    "position": "RB",
                    "team": "BUF",
                    "age": 22,
                    "years_exp": 0,
                }
            },
        )
        db.refresh(market)
        context = db.query(PlayerCurrentContext).filter(PlayerCurrentContext.source_player_id == sleeper_id).one()

    assert summary["mapped_by_draft_market"] == 1
    assert context.canonical_player_id == canonical_id
    assert market.canonical_player_id == canonical_id


def test_refresh_sleeper_context_creates_current_sleeper_universe_player(tmp_path):
    sleeper_id = f"slp-{uuid.uuid4().hex}"
    player_name = f"Rookie Seed {uuid.uuid4().hex[:8]}"
    duckdb_path = make_crosswalk_db(tmp_path, [])
    with SessionLocal() as db:
        summary = refresh_sleeper_context(
            season=2026,
            db=db,
            duckdb_path=duckdb_path,
            players={
                sleeper_id: {
                    "player_id": sleeper_id,
                    "full_name": player_name,
                    "position": "WR",
                    "team": "TEN",
                    "active": True,
                    "status": "Active",
                    "age": 21,
                    "years_exp": 0,
                }
            },
        )
        context = db.query(PlayerCurrentContext).filter(PlayerCurrentContext.source_player_id == sleeper_id).one()
        player = db.query(CanonicalPlayer).filter(CanonicalPlayer.canonical_player_id == context.canonical_player_id).one()
        season_row = db.query(PlayerSeason).filter(PlayerSeason.canonical_player_id == player.canonical_player_id).one()

    assert summary["canonical_created_for_sleeper_universe"] == 1
    assert summary["needs_review"] == 0
    assert player.full_name == player_name
    assert season_row.season == 2026
    assert season_row.team == "TEN"
    assert season_row.position == "WR"


def test_refresh_sleeper_context_flags_ambiguous_name_position_match(tmp_path):
    suffix = uuid.uuid4().hex
    sleeper_id = f"slp-{suffix}"
    player_name = f"Ambiguous Receiver {suffix[:8]}"
    duckdb_path = make_crosswalk_db(tmp_path, [])
    with SessionLocal() as db:
        db.add_all(
            [
                CanonicalPlayer(
                    canonical_player_id=f"nfl_justin_jefferson_a_{suffix}",
                    nflverse_player_id=None,
                    full_name=player_name,
                    normalized_name=normalize_player_name(player_name),
                ),
                CanonicalPlayer(
                    canonical_player_id=f"nfl_justin_jefferson_b_{suffix}",
                    nflverse_player_id=None,
                    full_name=player_name,
                    normalized_name=normalize_player_name(player_name),
                ),
            ]
        )
        db.flush()
        db.add_all(
            [
                PlayerSeason(
                    canonical_player_id=f"nfl_justin_jefferson_a_{suffix}",
                    season=2025,
                    team="MIN",
                    position="WR",
                ),
                PlayerSeason(
                    canonical_player_id=f"nfl_justin_jefferson_b_{suffix}",
                    season=2025,
                    team="ARI",
                    position="WR",
                ),
            ]
        )
        db.commit()

        summary = refresh_sleeper_context(
            season=2026,
            db=db,
            duckdb_path=duckdb_path,
            players={
                sleeper_id: {
                    "player_id": sleeper_id,
                    "full_name": player_name,
                    "position": "WR",
                    "team": "MIN",
                }
            },
        )
        context = db.query(PlayerCurrentContext).filter(PlayerCurrentContext.source_player_id == sleeper_id).one()
        mapping = db.query(ExternalPlayerMapping).filter(ExternalPlayerMapping.source_player_id == sleeper_id).one()

    assert summary["needs_review"] == 1
    assert context.canonical_player_id is None
    assert mapping.status == "needs_review"
