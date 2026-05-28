"""Tests for Sleeper ADP draft-market ingestion."""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from superagent.data.ingest_sleeper_adp import ingest_sleeper_adp
from superagent.db import SessionLocal, init_db
from superagent.models import CanonicalPlayer, DraftPlayerMarket, DraftSourceRank, ExternalPlayerMapping


init_db()


def sleeper_projection(player_id: str, name: str, position: str, team: str, ppr: float, two_qb: float | None = None):
    first, *rest = name.split(" ")
    return {
        "player_id": player_id,
        "season": "2026",
        "season_type": "regular",
        "team": team,
        "stats": {
            "adp_ppr": ppr,
            "adp_half_ppr": ppr + 0.5,
            "adp_std": ppr + 1,
            "adp_2qb": two_qb if two_qb is not None else ppr + 2,
        },
        "player": {
            "first_name": first,
            "last_name": " ".join(rest),
            "position": position,
            "team": team,
            "active": True,
            "status": "Active",
            "age": 21,
            "birth_date": "2005-01-01",
        },
    }


def test_ingest_sleeper_adp_creates_2026_market_rows_for_current_class():
    suffix = uuid.uuid4().hex[:8]
    source = f"sleeper-adp-test-{suffix}"
    projections = [
        sleeper_projection(f"love-{suffix}", "Jeremiyah Love", "RB", "ARI", 19.7),
        sleeper_projection(f"tate-{suffix}", "Carnell Tate", "WR", "TEN", 62.9),
        sleeper_projection(f"jordan-{suffix}", "Jordan Love", "QB", "GB", 124.8, two_qb=50.0),
        sleeper_projection(f"old-{suffix}", "Old Hidden", "WR", "FA", 999.0),
        sleeper_projection(f"idp-{suffix}", "IDP Hidden", "LB", "BUF", 120.0),
    ]

    with SessionLocal() as db:
        summary = ingest_sleeper_adp(
            season=2026,
            scoring="ppr",
            source=source,
            projections=projections,
            db=db,
            min_import_rows=3,
            max_adp=200,
        )
        markets = (
            db.query(DraftPlayerMarket)
            .filter(DraftPlayerMarket.source == source, DraftPlayerMarket.season == 2026)
            .order_by(DraftPlayerMarket.adp.asc())
            .all()
        )
        mappings = (
            db.query(ExternalPlayerMapping)
            .filter(ExternalPlayerMapping.source == "sleeper", ExternalPlayerMapping.season == 2026)
            .all()
        )
        market_ids = [market.id for market in markets]
        source_ranks = db.query(DraftSourceRank).filter(DraftSourceRank.market_id.in_(market_ids)).all()

    assert summary["rows_seen"] == 5
    assert summary["rows_imported"] == 3
    assert summary["skipped_no_adp"] == 1
    assert summary["skipped_position"] == 1
    assert [market.source_player_name for market in markets] == ["Jeremiyah Love", "Carnell Tate", "Jordan Love"]
    assert [market.position_rank for market in markets] == [1, 1, 1]
    assert markets[0].adp == 19.7
    assert all(market.canonical_player_id.startswith("sleeper_") for market in markets)
    assert all(db_mapping.status == "approved" for db_mapping in mappings if db_mapping.source_player_id.endswith(suffix))
    assert {rank.rank_source for rank in source_ranks} >= {"Sleeper PPR ADP", "Sleeper 2QB ADP"}


def test_ingest_sleeper_adp_reuses_existing_sleeper_mapping():
    suffix = uuid.uuid4().hex[:8]
    source = f"sleeper-adp-map-{suffix}"
    player_id = f"mapped-{suffix}"
    canonical_id = f"nfl_mapped_{suffix}"
    with SessionLocal() as db:
        db.add(
            CanonicalPlayer(
                canonical_player_id=canonical_id,
                nflverse_player_id=canonical_id,
                full_name="Mapped Back",
                normalized_name="mapped back",
            )
        )
        db.add(
            ExternalPlayerMapping(
                source="sleeper",
                season=2026,
                source_player_name="Mapped Back",
                source_player_id=player_id,
                canonical_player_id=canonical_id,
                confidence=1.0,
                status="approved",
            )
        )
        db.commit()
        summary = ingest_sleeper_adp(
            season=2026,
            source=source,
            projections=[sleeper_projection(player_id, "Mapped Back", "RB", "BUF", 88.0)],
            db=db,
            min_import_rows=1,
        )
        market = db.query(DraftPlayerMarket).filter(DraftPlayerMarket.source == source).one()

    assert summary["mapped_from_existing_sleeper_mapping"] == 1
    assert market.canonical_player_id == canonical_id
