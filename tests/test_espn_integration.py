"""
Tests for ESPN league ingestion.
"""

import sys
import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from superagent.api import app  # noqa: E402
from superagent.canonical_resolution import normalize_player_name  # noqa: E402
from superagent.espn_integration import ingest_espn_league  # noqa: E402
from superagent.models import (  # noqa: E402
    Base,
    CanonicalPlayer,
    CanonicalPlayerAlias,
    LeagueDraftPick,
    LeagueExternalSource,
    LeagueRosterPlayer,
    PlayerSeason,
)


client = TestClient(app)


class FakeSettings:
    name = "ESPN Home League"
    scoring_format = "PPR"
    team_count = 12


class FakePlayer:
    def __init__(self, name, position, slot="BE"):
        self.name = name
        self.position = position
        self.slot_position = slot


class FakeTeam:
    def __init__(self, name, roster):
        self.team_name = name
        self.roster = roster


class FakePick:
    def __init__(self, player, round_num, pick_num, team):
        self.player = player
        self.round_num = round_num
        self.pick_num = pick_num
        self.team = team


class FakeLeague:
    settings = FakeSettings()
    teams = [
        FakeTeam("Rob's Team", [FakePlayer("Josh Allen", "QB"), FakePlayer("James Cook", "RB")]),
        FakeTeam("Other Team", [FakePlayer("Mystery Rookie", "WR")]),
    ]
    draft = [
        FakePick(FakePlayer("Josh Allen", "QB"), 1, 1, "Rob's Team"),
        FakePick(FakePlayer("Mystery Rookie", "WR"), 1, 2, "Other Team"),
    ]


def add_player(db, player_id, name, team, position):
    player = CanonicalPlayer(
        canonical_player_id=player_id,
        nflverse_player_id=player_id,
        full_name=name,
        normalized_name=normalize_player_name(name),
    )
    db.add(player)
    db.flush()
    db.add(PlayerSeason(canonical_player_id=player_id, season=2025, team=team, position=position))
    db.add(
        CanonicalPlayerAlias(
            canonical_player_id=player_id,
            alias=name,
            normalized_alias=normalize_player_name(name),
            source="test",
        )
    )
    db.commit()


def test_ingest_espn_league_settings_rosters_and_draft():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with SessionLocal() as db:
        add_player(db, "nfl_josh_allen", "Josh Allen", "BUF", "QB")
        add_player(db, "nfl_james_cook", "James Cook", "BUF", "RB")

        result = ingest_espn_league(
            espn_league_id=12345,
            season=2025,
            user_id=1,
            db=db,
            espn_league=FakeLeague(),
        )

        assert result["ok"] is True
        assert result["league_name"] == "ESPN Home League"
        assert result["settings"]["ppr_type"] == "ppr"
        assert result["roster_players"] == 3
        assert result["roster_needing_review"] == 1
        assert result["draft_picks"] == 2
        assert db.query(LeagueExternalSource).count() == 1
        assert db.query(LeagueRosterPlayer).count() == 3
        assert db.query(LeagueDraftPick).count() == 2


def test_espn_sync_api_requires_auth():
    response = client.post(
        "/integrations/espn/leagues",
        json={"espn_league_id": 12345, "season": 2025},
    )

    assert response.status_code == 401


def test_espn_sync_api_calls_ingestion(monkeypatch):
    email = f"espn-{uuid.uuid4().hex}@example.com"
    registered = client.post(
        "/auth/register",
        json={"email": email, "password": "password123"},
    )
    token = registered.json()["token"]

    def fake_ingest(**kwargs):
        return {
            "ok": True,
            "league_id": 99,
            "source": "espn",
            "external_league_id": str(kwargs["espn_league_id"]),
            "season": kwargs["season"],
        }

    monkeypatch.setattr("superagent.api.ingest_espn_league", fake_ingest)

    response = client.post(
        "/integrations/espn/leagues",
        json={"espn_league_id": 12345, "season": 2025},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["source"] == "espn"
    assert response.json()["league_id"] == 99
