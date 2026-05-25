"""
Tests for Phase 10B strict DraftSheets ingestion.
"""

import csv
import sys
from pathlib import Path

import pytest
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from superagent.canonical_resolution import normalize_player_name
from superagent.data.ingest_draft_sheets import DraftIngestionError, ingest_draft_market_file
from superagent.models import (
    Base,
    CanonicalPlayer,
    CanonicalPlayerAlias,
    DraftImportReview,
    DraftMarketImport,
    DraftPlayerMarket,
    DraftSourceRank,
    PlayerSeason,
)


@pytest.fixture()
def db_session():
    """Create an isolated product DB for draft ingestion tests."""
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def add_player(db, player_id, name, team, position, season=2025, aliases=None):
    """Seed a canonical player for import mapping."""
    player = db.query(CanonicalPlayer).filter(
        CanonicalPlayer.canonical_player_id == player_id
    ).first()
    if player is None:
        player = CanonicalPlayer(
            canonical_player_id=player_id,
            nflverse_player_id=player_id.replace("nfl_", ""),
            full_name=name,
            normalized_name=normalize_player_name(name),
        )
        db.add(player)
        db.flush()
    db.add(
        PlayerSeason(
            canonical_player_id=player_id,
            season=season,
            team=team,
            position=position,
        )
    )
    existing_aliases = {
        alias.normalized_alias
        for alias in db.query(CanonicalPlayerAlias).filter(
            CanonicalPlayerAlias.canonical_player_id == player_id
        )
    }
    for alias in aliases or [name]:
        normalized_alias = normalize_player_name(alias)
        if normalized_alias in existing_aliases:
            continue
        db.add(
            CanonicalPlayerAlias(
                canonical_player_id=player_id,
                alias=alias,
                normalized_alias=normalized_alias,
                source="test",
            )
        )
    db.commit()


def seed_players(db):
    add_player(db, "nfl_josh_allen", "Josh Allen", "BUF", "QB", aliases=["Josh Allen", "Joshua Allen"])
    add_player(db, "nfl_lamar_jackson", "Lamar Jackson", "BAL", "QB")
    add_player(db, "nfl_jamarr_chase", "Ja'Marr Chase", "CIN", "WR")
    add_player(db, "nfl_bijan_robinson", "Bijan Robinson", "ATL", "RB")
    add_player(db, "nfl_gabe_davis", "Gabe Davis", "JAX", "WR", aliases=["Gabe Davis", "Gabriel Davis"])
    add_player(db, "nfl_kenneth_walker", "Kenneth Walker III", "SEA", "RB", aliases=["Kenneth Walker", "Ken Walker"])
    add_player(db, "nfl_travis_hunter", "Travis Hunter", "JAX", "WR")
    add_player(db, "nfl_taysom_hill", "Taysom Hill", "NO", "TE", season=2024)
    add_player(db, "nfl_taysom_hill", "Taysom Hill", "NO", "RB", season=2025, aliases=["Taysom Hill"])
    add_player(db, "nfl_brock_bowers", "Brock Bowers", "LV", "TE")
    add_player(db, "nfl_cee_dee_lamb", "CeeDee Lamb", "DAL", "WR")


def write_csv(path, rows, headers=None):
    headers = headers or [
        "Rank",
        "Player",
        "Team",
        "Bye",
        "POS",
        "ESPN",
        "Sleeper",
        "AVG",
        "Fpros ECR",
        "ADP",
        "Floor",
        "Ceiling",
        "Value",
        "Injury Risk",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def base_rows():
    return [
        {
            "Rank": 1,
            "Player": "Josh Allen",
            "Team": "BUF",
            "Bye": 7,
            "POS": "QB1",
            "ESPN": 21,
            "Sleeper": 23,
            "AVG": 22,
            "Fpros ECR": 25,
            "ADP": 24,
            "Floor": 303.9,
            "Ceiling": 387.8,
            "Value": 88.7,
            "Injury Risk": "Low Risk",
        },
        {
            "Rank": 2,
            "Player": "Lamar Jackson",
            "Team": "BAL",
            "Bye": 7,
            "POS": "QB2",
            "ESPN": 27,
            "Sleeper": 25,
            "AVG": 26,
            "Fpros ECR": 27,
            "ADP": 26,
            "Floor": 295.0,
            "Ceiling": 385.3,
            "Value": 86.0,
            "Injury Risk": "Low Risk",
        },
    ]


def test_valid_csv_imports_players_and_source_ranks(db_session, tmp_path):
    seed_players(db_session)
    csv_path = tmp_path / "draftsheets.csv"
    write_csv(csv_path, base_rows())

    result = ingest_draft_market_file(str(csv_path), "draftsheetsv6", 2025, db=db_session)

    markets = db_session.query(DraftPlayerMarket).all()
    ranks = db_session.query(DraftSourceRank).all()
    assert result["ok"] is True
    assert result["rows_seen"] == 2
    assert result["rows_imported"] == 2
    assert result["rows_needing_review"] == 0
    assert len(markets) == 2
    assert {market.canonical_player_id for market in markets} == {"nfl_josh_allen", "nfl_lamar_jackson"}
    assert len(ranks) == 6


def test_duplicate_name_variation_resolves_to_same_player(db_session, tmp_path):
    seed_players(db_session)
    csv_path = tmp_path / "gabe.csv"
    write_csv(
        csv_path,
        [
            {
                "Rank": 80,
                "Player": "Gabriel Davis",
                "Team": "JAX",
                "Bye": 8,
                "POS": "WR45",
                "AVG": 80,
                "Fpros ECR": 82,
            }
        ],
    )

    result = ingest_draft_market_file(str(csv_path), "draftsheetsv6", 2025, db=db_session)

    market = db_session.query(DraftPlayerMarket).first()
    assert result["rows_imported"] == 1
    assert market.canonical_player_id == "nfl_gabe_davis"
    assert market.position == "WR"
    assert market.position_rank == 45


def test_typo_is_flagged_for_review_not_guessed(db_session, tmp_path):
    seed_players(db_session)
    csv_path = tmp_path / "typo.csv"
    write_csv(
        csv_path,
        [
            {
                "Rank": 1,
                "Player": "J. Al",
                "Team": "BUF",
                "Bye": 7,
                "POS": "QB1",
                "AVG": 1,
            }
        ],
    )

    result = ingest_draft_market_file(str(csv_path), "draftsheetsv6", 2025, db=db_session)

    review = db_session.query(DraftImportReview).first()
    assert result["rows_imported"] == 0
    assert result["rows_needing_review"] == 1
    assert review is not None
    assert review.source_player_name == "J. Al"


def test_missing_required_column_hard_fails(db_session, tmp_path):
    seed_players(db_session)
    csv_path = tmp_path / "missing.csv"
    write_csv(csv_path, [{"Player": "Josh Allen", "Team": "BUF"}], headers=["Player", "Team"])

    with pytest.raises(DraftIngestionError, match="Missing required column"):
        ingest_draft_market_file(str(csv_path), "draftsheetsv6", 2025, db=db_session)


def test_invalid_adp_value_hard_fails(db_session, tmp_path):
    seed_players(db_session)
    csv_path = tmp_path / "bad_adp.csv"
    rows = base_rows()
    rows[0]["ADP"] = "not-a-number"
    write_csv(csv_path, rows)

    with pytest.raises(DraftIngestionError, match="invalid numeric value"):
        ingest_draft_market_file(str(csv_path), "draftsheetsv6", 2025, db=db_session)


def test_optional_source_rank_error_marker_is_ignored(db_session, tmp_path):
    seed_players(db_session)
    csv_path = tmp_path / "optional_error.csv"
    rows = base_rows()
    rows[0]["Sleeper"] = "#N/A"
    write_csv(csv_path, rows)

    result = ingest_draft_market_file(str(csv_path), "draftsheetsv6", 2025, db=db_session)

    assert result["rows_imported"] == 2
    josh_market = db_session.query(DraftPlayerMarket).filter(
        DraftPlayerMarket.canonical_player_id == "nfl_josh_allen"
    ).first()
    rank_sources = {rank.rank_source for rank in josh_market.source_ranks}
    assert "ESPN" in rank_sources
    assert "Sleeper" not in rank_sources


def test_new_rookie_not_in_canonical_identity_goes_to_review(db_session, tmp_path):
    seed_players(db_session)
    csv_path = tmp_path / "rookie.csv"
    write_csv(
        csv_path,
        [{"Rank": 150, "Player": "Future Rookie", "Team": "BUF", "Bye": 7, "POS": "RB55", "AVG": 150}],
    )

    result = ingest_draft_market_file(str(csv_path), "draftsheetsv6", 2025, db=db_session)

    assert result["rows_imported"] == 0
    assert result["rows_needing_review"] == 1
    assert db_session.query(DraftImportReview).first().source_player_name == "Future Rookie"


def test_position_change_uses_season_context(db_session, tmp_path):
    seed_players(db_session)
    csv_path = tmp_path / "position_change.csv"
    write_csv(
        csv_path,
        [{"Rank": 160, "Player": "Taysom Hill", "Team": "NO", "Bye": 11, "POS": "RB60", "AVG": 160}],
    )

    result = ingest_draft_market_file(str(csv_path), "draftsheetsv6", 2025, db=db_session)

    market = db_session.query(DraftPlayerMarket).first()
    assert result["rows_imported"] == 1
    assert market.canonical_player_id == "nfl_taysom_hill"
    assert market.position == "RB"


def test_xlsx_data_sheet_imports_draftsheets_shape(db_session, tmp_path):
    seed_players(db_session)
    xlsx_path = tmp_path / "draftsheets.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "DATA"
    sheet.append(["Rank", "Player", "Team", "Bye", "POS", "ESPN", "Sleeper", "NFL", "AVG", "Yahoo", "Fpros ECR"])
    sheet.append([1, "Ja'Marr Chase", "CIN", 10, "WR1", 1, 1, 1, 1, 1, 1])
    sheet.append([2, "Bijan Robinson", "ATL", 5, "RB1", 2, 3, 2, 2.2, 2, 2])
    workbook.save(xlsx_path)

    result = ingest_draft_market_file(str(xlsx_path), "draftsheetsv6", 2025, db=db_session)

    import_batch = db_session.query(DraftMarketImport).first()
    assert result["rows_imported"] == 2
    assert result["sheet_name"] == "DATA"
    assert import_batch.sheet_name == "DATA"
    assert db_session.query(DraftSourceRank).count() == 10
