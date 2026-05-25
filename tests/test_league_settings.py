"""
Tests for Phase 10C league settings and draft value adjustment.
"""

import sys
import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from superagent.api import app  # noqa: E402
from superagent.draft_value import adjust_draft_value  # noqa: E402
from superagent.models import Base, DraftPlayerMarket, LeagueSettings  # noqa: E402


client = TestClient(app)


def auth_headers(email_prefix: str = "league") -> dict:
    response = client.post(
        "/auth/register",
        json={
            "email": f"{email_prefix}-{uuid.uuid4().hex}@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']}"}


def league_payload(**overrides):
    payload = {
        "league_name": "Rob's Home League",
        "league_type": "snake",
        "settings": {
            "ppr_type": "ppr",
            "num_teams": 12,
            "roster_spots": 16,
            "qb_slots": 1,
            "rb_slots": 2,
            "wr_slots": 2,
            "te_slots": 1,
            "flex_slots": 1,
            "superflex_slots": 0,
            "bench_spots": 6,
            "taxi_spots": 0,
            "passing_td_points": 4,
            "rushing_td_points": 6,
            "receiving_td_points": 6,
            "pass_yards_per_point": 25,
            "rush_yards_per_point": 10,
            "receiving_yards_per_point": 10,
        },
    }
    settings_overrides = overrides.pop("settings", None)
    payload.update(overrides)
    if settings_overrides:
        payload["settings"].update(settings_overrides)
    return payload


def test_create_league_with_ppr_settings():
    headers = auth_headers()

    response = client.post("/leagues", json=league_payload(), headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["league_name"] == "Rob's Home League"
    assert data["league_type"] == "snake"
    assert data["settings"]["ppr_type"] == "ppr"
    assert data["settings"]["num_teams"] == 12


def test_retrieve_league_settings_match():
    headers = auth_headers()
    created = client.post(
        "/leagues",
        json=league_payload(settings={"ppr_type": "half_ppr", "superflex_slots": 1}),
        headers=headers,
    )
    league_id = created.json()["id"]

    response = client.get(f"/leagues/{league_id}", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == league_id
    assert data["settings"]["ppr_type"] == "half_ppr"
    assert data["settings"]["superflex_slots"] == 1


def test_update_league_scoring_settings():
    headers = auth_headers()
    created = client.post(
        "/leagues",
        json=league_payload(settings={"passing_td_points": 6}),
        headers=headers,
    )
    league_id = created.json()["id"]

    response = client.put(
        f"/leagues/{league_id}",
        json=league_payload(
            league_name="Updated League",
            league_type="auction",
            settings={"passing_td_points": 4, "ppr_type": "standard"},
        ),
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["league_name"] == "Updated League"
    assert data["league_type"] == "auction"
    assert data["settings"]["passing_td_points"] == 4
    assert data["settings"]["ppr_type"] == "standard"


def test_cannot_read_or_update_other_users_league():
    owner_headers = auth_headers("owner")
    other_headers = auth_headers("other")
    created = client.post("/leagues", json=league_payload(), headers=owner_headers)
    league_id = created.json()["id"]

    read_response = client.get(f"/leagues/{league_id}", headers=other_headers)
    update_response = client.put(f"/leagues/{league_id}", json=league_payload(), headers=other_headers)

    assert read_response.status_code == 404
    assert update_response.status_code == 404


def test_invalid_league_settings_rejected():
    headers = auth_headers()

    response = client.post(
        "/leagues",
        json=league_payload(settings={"ppr_type": "triple_ppr"}),
        headers=headers,
    )

    assert response.status_code == 400


def test_multiple_leagues_per_user():
    headers = auth_headers()
    first = client.post("/leagues", json=league_payload(league_name="Home"), headers=headers)
    second = client.post("/leagues", json=league_payload(league_name="Work"), headers=headers)

    response = client.get("/leagues", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    names = {league["league_name"] for league in response.json()}
    assert {"Home", "Work"}.issubset(names)


def test_qb_value_shifts_in_superflex_and_six_point_pass_td():
    market = DraftPlayerMarket(
        source="draftsheetsv6",
        season=2025,
        canonical_player_id="nfl_josh_allen",
        source_player_name="Josh Allen",
        position="QB",
        value=40,
    )
    standard = LeagueSettings(ppr_type="ppr", superflex_slots=0, passing_td_points=4)
    superflex = LeagueSettings(ppr_type="ppr", superflex_slots=1, passing_td_points=6)

    standard_value = adjust_draft_value(market, standard)
    superflex_value = adjust_draft_value(market, superflex)

    assert superflex_value["adjusted_value"] > standard_value["adjusted_value"]
    assert superflex_value["league_adjustment"] == 29.0


def test_ppr_value_shifts_receiving_positions_more_than_qb():
    rb_market = DraftPlayerMarket(
        source="draftsheetsv6",
        season=2025,
        canonical_player_id="nfl_james_cook",
        source_player_name="James Cook",
        position="RB",
        value=20,
    )
    wr_market = DraftPlayerMarket(
        source="draftsheetsv6",
        season=2025,
        canonical_player_id="nfl_khalil_shakir",
        source_player_name="Khalil Shakir",
        position="WR",
        value=20,
    )
    qb_market = DraftPlayerMarket(
        source="draftsheetsv6",
        season=2025,
        canonical_player_id="nfl_josh_allen",
        source_player_name="Josh Allen",
        position="QB",
        value=20,
    )
    standard = LeagueSettings(ppr_type="standard", flex_slots=1)
    ppr = LeagueSettings(ppr_type="ppr", flex_slots=1)

    rb_delta = adjust_draft_value(rb_market, ppr)["adjusted_value"] - adjust_draft_value(rb_market, standard)["adjusted_value"]
    wr_delta = adjust_draft_value(wr_market, ppr)["adjusted_value"] - adjust_draft_value(wr_market, standard)["adjusted_value"]
    qb_delta = adjust_draft_value(qb_market, ppr)["adjusted_value"] - adjust_draft_value(qb_market, standard)["adjusted_value"]

    assert wr_delta > rb_delta > qb_delta


def test_league_tables_create_in_isolated_db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    with SessionLocal() as db:
        assert db.query(LeagueSettings).count() == 0
