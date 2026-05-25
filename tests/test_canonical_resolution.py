"""
Tests for Phase 10A canonical player identity.
"""

import sys
from pathlib import Path

import duckdb
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from superagent.canonical_resolution import (
    auto_map_external_player,
    normalize_player_name,
    resolve_to_canonical,
    seed_canonical_players_from_nflverse,
)
from superagent.models import (
    Base,
    CanonicalPlayer,
    CanonicalPlayerAlias,
    DraftImportReview,
    ExternalPlayerMapping,
    PlayerSeason,
)


@pytest.fixture()
def db_session():
    """Create an isolated product DB for canonical identity tests."""
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def add_player(
    db,
    canonical_player_id,
    full_name,
    season=2024,
    team="BUF",
    position="QB",
    nflverse_player_id=None,
    aliases=None,
):
    """Add a canonical player with season context and aliases."""
    player = CanonicalPlayer(
        canonical_player_id=canonical_player_id,
        nflverse_player_id=nflverse_player_id,
        full_name=full_name,
        normalized_name=normalize_player_name(full_name),
    )
    db.add(player)
    db.flush()
    db.add(
        PlayerSeason(
            canonical_player_id=canonical_player_id,
            season=season,
            team=team,
            position=position,
        )
    )
    for alias in aliases or [full_name]:
        db.add(
            CanonicalPlayerAlias(
                canonical_player_id=canonical_player_id,
                alias=alias,
                normalized_alias=normalize_player_name(alias),
                source="test",
            )
        )
    db.commit()
    return player


def test_resolve_to_canonical_exact_match(db_session):
    add_player(
        db_session,
        "nfl_00_0034857",
        "Josh Allen",
        nflverse_player_id="00-0034857",
    )

    result = resolve_to_canonical("Josh Allen", 2024, position="QB", db=db_session)

    assert result["ok"] is True
    assert result["canonical_player_id"] == "nfl_00_0034857"
    assert result["confidence"] == 1.0
    assert result["team"] == "BUF"


def test_resolve_to_canonical_fuzzy_match(db_session):
    add_player(
        db_session,
        "nfl_gabe_davis",
        "Gabe Davis",
        team="JAX",
        position="WR",
        aliases=["Gabe Davis"],
    )

    result = resolve_to_canonical("Gabriel Davis", 2024, position="WR", db=db_session)

    assert result["ok"] is True
    assert result["canonical_player_id"] == "nfl_gabe_davis"
    assert result["confidence"] >= 0.85


def test_josh_allen_qb_vs_defender_disambiguation(db_session):
    add_player(
        db_session,
        "nfl_00_0034857",
        "Josh Allen",
        team="BUF",
        position="QB",
        aliases=["Josh Allen", "J. Allen"],
    )
    add_player(
        db_session,
        "nfl_00_0034793",
        "Josh Hines-Allen",
        team="JAX",
        position="DE",
        aliases=["Josh Allen", "Josh Hines-Allen"],
    )

    ambiguous = resolve_to_canonical("Josh Allen", 2024, db=db_session)
    qb_result = resolve_to_canonical("Josh Allen", 2024, position="QB", db=db_session)

    assert ambiguous["ok"] is False
    assert ambiguous["needs_review"] is True
    assert len(ambiguous["candidates"]) == 2
    assert qb_result["ok"] is True
    assert qb_result["canonical_player_id"] == "nfl_00_0034857"
    assert qb_result["position"] == "QB"


def test_ken_kenneth_variation(db_session):
    add_player(
        db_session,
        "nfl_kenneth_walker",
        "Kenneth Walker III",
        team="SEA",
        position="RB",
        aliases=["Kenneth Walker III", "Ken Walker"],
    )

    result = resolve_to_canonical("Ken Walker", 2024, position="RB", db=db_session)

    assert result["ok"] is True
    assert result["canonical_player_id"] == "nfl_kenneth_walker"


def test_auto_mapping_high_confidence(db_session):
    add_player(
        db_session,
        "nfl_00_0034857",
        "Josh Allen",
        nflverse_player_id="00-0034857",
    )

    result = auto_map_external_player(
        "draftsheetsv6",
        2024,
        "Josh Allen",
        source_player_id="ds-1",
        position="QB",
        db=db_session,
    )
    repeat = auto_map_external_player(
        "draftsheetsv6",
        2024,
        "Josh Allen",
        source_player_id="ds-1",
        position="QB",
        db=db_session,
    )

    mappings = db_session.query(ExternalPlayerMapping).all()
    assert result["ok"] is True
    assert repeat["ok"] is True
    assert result["status"] == "auto"
    assert len(mappings) == 1
    assert mappings[0].canonical_player_id == "nfl_00_0034857"


def test_auto_mapping_low_confidence_flagged_for_review(db_session):
    add_player(db_session, "nfl_josh_allen", "Josh Allen", position="QB")
    add_player(db_session, "nfl_davante_adams", "Davante Adams", team="LV", position="WR")

    result = auto_map_external_player("espn", 2025, "J.A.", db=db_session)

    review = db_session.query(DraftImportReview).first()
    assert result["ok"] is False
    assert result["needs_review"] is True
    assert review is not None
    assert review.source_player_name == "J.A."


def create_seed_duckdb(path):
    """Create a tiny DuckDB with the tables needed by the seed function."""
    conn = duckdb.connect(str(path))
    conn.execute(
        """
        CREATE TABLE rosters (
            season INTEGER,
            gsis_id VARCHAR,
            full_name VARCHAR,
            football_name VARCHAR,
            team VARCHAR,
            position VARCHAR,
            age INTEGER
        )
        """
    )
    conn.execute(
        """
        INSERT INTO rosters VALUES
            (2024, '00-0034857', 'Joshua Allen', 'Josh Allen', 'BUF', 'QB', 28),
            (2024, '00-0033906', 'Gabriel Davis', 'Gabe Davis', 'JAX', 'WR', 25)
        """
    )
    conn.execute(
        """
        CREATE TABLE weekly (
            season INTEGER,
            player_id VARCHAR,
            player_display_name VARCHAR,
            player_name VARCHAR
        )
        """
    )
    conn.execute(
        """
        INSERT INTO weekly VALUES
            (2024, '00-0034857', 'Josh Allen', 'J.Allen'),
            (2024, '00-0033906', 'Gabe Davis', 'G.Davis')
        """
    )
    conn.execute(
        """
        CREATE TABLE plays (
            season INTEGER,
            passer_player_id VARCHAR,
            passer_player_name VARCHAR,
            rusher_player_id VARCHAR,
            rusher_player_name VARCHAR,
            receiver_player_id VARCHAR,
            receiver_player_name VARCHAR
        )
        """
    )
    conn.execute(
        """
        INSERT INTO plays VALUES
            (2024, '00-0034857', 'J. Allen', NULL, NULL, '00-0033906', 'G. Davis')
        """
    )
    conn.close()


def test_seed_from_nflverse_rosters_and_aliases(db_session, tmp_path):
    duckdb_path = tmp_path / "seed.duckdb"
    create_seed_duckdb(duckdb_path)

    summary = seed_canonical_players_from_nflverse(
        seasons=[2024],
        db=db_session,
        duckdb_path=str(duckdb_path),
    )

    players = db_session.query(CanonicalPlayer).all()
    seasons = db_session.query(PlayerSeason).all()
    aliases = {
        alias.alias
        for alias in db_session.query(CanonicalPlayerAlias).all()
    }
    assert summary["players_created"] == 2
    assert len(players) == 2
    assert len(seasons) == 2
    assert "Joshua Allen" in aliases
    assert "Josh Allen" in aliases
    assert "J. Allen" in aliases
    assert "G. Davis" in aliases


def test_seed_uses_existing_canonical_id_when_nflverse_id_matches(db_session, tmp_path):
    duckdb_path = tmp_path / "seed_existing.duckdb"
    create_seed_duckdb(duckdb_path)
    add_player(
        db_session,
        "nfl_existing_josh_allen",
        "Josh Allen",
        nflverse_player_id="00-0034857",
    )

    summary = seed_canonical_players_from_nflverse(
        seasons=[2024],
        db=db_session,
        duckdb_path=str(duckdb_path),
    )

    alias = (
        db_session.query(CanonicalPlayerAlias)
        .filter(CanonicalPlayerAlias.alias == "Joshua Allen")
        .first()
    )
    season = (
        db_session.query(PlayerSeason)
        .filter(
            PlayerSeason.canonical_player_id == "nfl_existing_josh_allen",
            PlayerSeason.season == 2024,
        )
        .first()
    )
    assert summary["players_seen"] == 2
    assert alias is not None
    assert alias.canonical_player_id == "nfl_existing_josh_allen"
    assert season is not None


def test_multiple_sources_for_same_player(db_session):
    add_player(db_session, "nfl_00_0034857", "Josh Allen", nflverse_player_id="00-0034857")

    first = auto_map_external_player("sleeper", 2024, "Josh Allen", position="QB", db=db_session)
    second = auto_map_external_player("draftsheetsv6", 2024, "Joshua Allen", position="QB", db=db_session)

    mappings = db_session.query(ExternalPlayerMapping).all()
    assert first["ok"] is True
    assert second["ok"] is True
    assert len(mappings) == 2
    assert {mapping.canonical_player_id for mapping in mappings} == {"nfl_00_0034857"}
