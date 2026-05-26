"""Refresh current NFL player context from Sleeper.

Sleeper is used as a current-context provider, not as the canonical identity
system. We map Sleeper player ids into Superagent canonical players through the
nflverse roster crosswalk first, then fall back to draft-market/canonical data
and finally exact name+position matching.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from typing import Any

import duckdb
import requests
from sqlalchemy.orm import Session

from superagent.canonical_resolution import canonical_id_from_nflverse, normalize_player_name
from superagent.config import get_config
from superagent.db import SessionLocal
from superagent.models import (
    CanonicalPlayer,
    CanonicalPlayerAlias,
    DraftPlayerMarket,
    ExternalPlayerMapping,
    PlayerCurrentContext,
    PlayerSeason,
    utc_now,
)


SLEEPER_PLAYERS_URL = "https://api.sleeper.app/v1/players/nfl"
SOURCE = "sleeper"


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _fetch_sleeper_players() -> dict[str, dict[str, Any]]:
    response = requests.get(SLEEPER_PLAYERS_URL, timeout=45)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("Sleeper players response was not an object")
    return data


def _load_sleeper_crosswalk(duckdb_path: str | None = None, max_season: int | None = None) -> dict[str, str]:
    """Return sleeper_id -> canonical_player_id from nflverse roster rows."""
    config = get_config()
    path = duckdb_path or str(config.DATABASE_PATH)
    conn = duckdb.connect(path)
    try:
        where = "sleeper_id IS NOT NULL AND gsis_id IS NOT NULL"
        params: list[Any] = []
        if max_season is not None:
            where += " AND season <= ?"
            params.append(max_season)
        rows = conn.execute(
            f"""
            SELECT season, sleeper_id, gsis_id, full_name
            FROM rosters
            WHERE {where}
            ORDER BY season DESC
            """,
            params,
        ).fetchall()
    finally:
        conn.close()

    crosswalk: dict[str, str] = {}
    for _season, sleeper_id, gsis_id, full_name in rows:
        sleeper_id = _safe_str(sleeper_id)
        gsis_id = _safe_str(gsis_id)
        if not sleeper_id or not gsis_id or sleeper_id in crosswalk:
            continue
        crosswalk[sleeper_id] = canonical_id_from_nflverse(gsis_id, _safe_str(full_name) or gsis_id)
    return crosswalk


def _canonical_exists(db: Session, canonical_player_id: str | None) -> bool:
    if not canonical_player_id:
        return False
    return (
        db.query(CanonicalPlayer.canonical_player_id)
        .filter(CanonicalPlayer.canonical_player_id == canonical_player_id)
        .first()
        is not None
    )


def _latest_positions(db: Session, season: int) -> dict[str, str | None]:
    rows = (
        db.query(PlayerSeason)
        .filter(PlayerSeason.season <= season)
        .order_by(PlayerSeason.season.desc(), PlayerSeason.id.desc())
        .all()
    )
    positions: dict[str, str | None] = {}
    for row in rows:
        positions.setdefault(row.canonical_player_id, row.position)
    return positions


def _name_position_index(db: Session, season: int) -> dict[tuple[str, str | None], set[str]]:
    positions = _latest_positions(db, season)
    index: dict[tuple[str, str | None], set[str]] = defaultdict(set)
    for player in db.query(CanonicalPlayer).all():
        position = positions.get(player.canonical_player_id)
        index[(player.normalized_name, position)].add(player.canonical_player_id)
    for alias in db.query(CanonicalPlayerAlias).all():
        position = positions.get(alias.canonical_player_id)
        index[(alias.normalized_alias, position)].add(alias.canonical_player_id)
    return index


def _draft_market_index(db: Session, season: int) -> dict[tuple[str, str | None], list[DraftPlayerMarket]]:
    index: dict[tuple[str, str | None], list[DraftPlayerMarket]] = defaultdict(list)
    for row in db.query(DraftPlayerMarket).filter(DraftPlayerMarket.season == season).all():
        index[(normalize_player_name(row.source_player_name), row.position)].append(row)
    return index


def _upsert_external_mapping(
    db: Session,
    *,
    season: int,
    source_player_id: str,
    source_player_name: str,
    canonical_player_id: str | None,
    confidence: float,
    status: str,
) -> None:
    mapping = (
        db.query(ExternalPlayerMapping)
        .filter(
            ExternalPlayerMapping.source == SOURCE,
            ExternalPlayerMapping.season == season,
            ExternalPlayerMapping.source_player_name == source_player_name,
            ExternalPlayerMapping.source_player_id == source_player_id,
        )
        .first()
    )
    if mapping is None:
        mapping = ExternalPlayerMapping(
            source=SOURCE,
            season=season,
            source_player_name=source_player_name,
            source_player_id=source_player_id,
        )
        db.add(mapping)
    mapping.canonical_player_id = canonical_player_id
    mapping.confidence = confidence
    mapping.status = status


def _ensure_sleeper_canonical(
    db: Session,
    *,
    player_id: str,
    full_name: str,
    position: str | None,
    season: int,
    team: str | None,
    age: int | None,
    birth_date: str | None,
) -> str:
    canonical_player_id = f"sleeper_{player_id}"
    player = db.query(CanonicalPlayer).filter(CanonicalPlayer.canonical_player_id == canonical_player_id).first()
    if player is None:
        player = CanonicalPlayer(
            canonical_player_id=canonical_player_id,
            nflverse_player_id=None,
            full_name=full_name,
            normalized_name=normalize_player_name(full_name),
            birth_date=birth_date,
        )
        db.add(player)
        db.flush()
    elif birth_date and not player.birth_date:
        player.birth_date = birth_date

    season_row = (
        db.query(PlayerSeason)
        .filter(
            PlayerSeason.canonical_player_id == canonical_player_id,
            PlayerSeason.season == season,
            PlayerSeason.team == team,
            PlayerSeason.position == position,
        )
        .first()
    )
    if season_row is None:
        db.add(
            PlayerSeason(
                canonical_player_id=canonical_player_id,
                season=season,
                team=team,
                position=position,
                age=age,
                status="active",
            )
        )

    normalized = normalize_player_name(full_name)
    alias = (
        db.query(CanonicalPlayerAlias)
        .filter(
            CanonicalPlayerAlias.canonical_player_id == canonical_player_id,
            CanonicalPlayerAlias.normalized_alias == normalized,
            CanonicalPlayerAlias.source == SOURCE,
        )
        .first()
    )
    if alias is None and normalized:
        db.add(
            CanonicalPlayerAlias(
                canonical_player_id=canonical_player_id,
                alias=full_name,
                normalized_alias=normalized,
                source=SOURCE,
            )
        )
    return canonical_player_id


def _resolve_context_player(
    db: Session,
    *,
    player_id: str,
    player: dict[str, Any],
    season: int,
    crosswalk: dict[str, str],
    draft_index: dict[tuple[str, str | None], list[DraftPlayerMarket]],
    name_index: dict[tuple[str, str | None], set[str]],
) -> tuple[str | None, float, str, str]:
    full_name = _safe_str(player.get("full_name")) or " ".join(
        part for part in [_safe_str(player.get("first_name")), _safe_str(player.get("last_name"))] if part
    )
    normalized = normalize_player_name(full_name)
    position = _safe_str(player.get("position"))
    team = _safe_str(player.get("team"))
    age = _safe_int(player.get("age"))
    birth_date = _safe_str(player.get("birth_date"))

    canonical_player_id = crosswalk.get(player_id)
    if canonical_player_id and _canonical_exists(db, canonical_player_id):
        return canonical_player_id, 1.0, "approved", "sleeper_id_crosswalk"

    draft_rows = draft_index.get((normalized, position), [])
    mapped_draft_rows = [row for row in draft_rows if row.canonical_player_id]
    mapped_ids = {row.canonical_player_id for row in mapped_draft_rows if row.canonical_player_id}
    if len(mapped_ids) == 1:
        canonical_player_id = next(iter(mapped_ids))
        return canonical_player_id, 0.92, "approved", "draft_market_match"
    if draft_rows and not mapped_ids and full_name:
        canonical_player_id = _ensure_sleeper_canonical(
            db,
            player_id=player_id,
            full_name=full_name,
            position=position,
            season=season,
            team=team,
            age=age,
            birth_date=birth_date,
        )
        for row in draft_rows:
            row.canonical_player_id = canonical_player_id
        return canonical_player_id, 0.85, "approved", "draftable_created"

    candidates = name_index.get((normalized, position), set())
    if len(candidates) == 1:
        return next(iter(candidates)), 0.8, "approved", "name_position_match"
    if len(candidates) > 1:
        return None, 0.4, "needs_review", "ambiguous_name_position"
    return None, 0.0, "needs_review", "unmapped"


def refresh_sleeper_context(
    *,
    season: int,
    db: Session | None = None,
    players: dict[str, dict[str, Any]] | None = None,
    duckdb_path: str | None = None,
) -> dict[str, Any]:
    """Refresh Sleeper current context into the product database."""
    owns_db = db is None
    db = db or SessionLocal()
    try:
        sleeper_players = players or _fetch_sleeper_players()
        crosswalk = _load_sleeper_crosswalk(duckdb_path=duckdb_path, max_season=season)
        draft_index = _draft_market_index(db, season)
        name_index = _name_position_index(db, season)
        existing_contexts = {
            row.source_player_id: row
            for row in db.query(PlayerCurrentContext)
            .filter(PlayerCurrentContext.source == SOURCE, PlayerCurrentContext.season == season)
            .all()
        }

        summary = {
            "source": SOURCE,
            "season": season,
            "players_seen": 0,
            "contexts_created": 0,
            "contexts_updated": 0,
            "mapped_by_crosswalk": 0,
            "mapped_by_draft_market": 0,
            "canonical_created_for_draftable": 0,
            "mapped_by_name_position": 0,
            "needs_review": 0,
            "free_agents": 0,
            "team_changes_vs_latest_season": 0,
        }

        latest_teams = {}
        for row in (
            db.query(PlayerSeason)
            .filter(PlayerSeason.season <= season)
            .order_by(PlayerSeason.season.desc(), PlayerSeason.id.desc())
            .all()
        ):
            latest_teams.setdefault(row.canonical_player_id, row.team)

        for player_id, player in sleeper_players.items():
            if not isinstance(player, dict):
                continue
            player_id = str(player_id)
            full_name = _safe_str(player.get("full_name")) or " ".join(
                part for part in [_safe_str(player.get("first_name")), _safe_str(player.get("last_name"))] if part
            )
            if not full_name:
                continue
            position = _safe_str(player.get("position"))
            if position not in {"QB", "RB", "WR", "TE", "K", "DEF", "DST"}:
                continue

            summary["players_seen"] += 1
            canonical_player_id, confidence, status, reason = _resolve_context_player(
                db,
                player_id=player_id,
                player=player,
                season=season,
                crosswalk=crosswalk,
                draft_index=draft_index,
                name_index=name_index,
            )
            if reason == "sleeper_id_crosswalk":
                summary["mapped_by_crosswalk"] += 1
            elif reason == "draft_market_match":
                summary["mapped_by_draft_market"] += 1
            elif reason == "draftable_created":
                summary["canonical_created_for_draftable"] += 1
            elif reason == "name_position_match":
                summary["mapped_by_name_position"] += 1
            if status == "needs_review":
                summary["needs_review"] += 1

            team = _safe_str(player.get("team"))
            if team is None:
                summary["free_agents"] += 1
            if canonical_player_id and team and latest_teams.get(canonical_player_id) and latest_teams[canonical_player_id] != team:
                summary["team_changes_vs_latest_season"] += 1

            _upsert_external_mapping(
                db,
                season=season,
                source_player_id=player_id,
                source_player_name=full_name,
                canonical_player_id=canonical_player_id,
                confidence=confidence,
                status=status,
            )

            context = existing_contexts.get(player_id)
            if context is None:
                context = PlayerCurrentContext(source=SOURCE, season=season, source_player_id=player_id)
                db.add(context)
                existing_contexts[player_id] = context
                summary["contexts_created"] += 1
            else:
                summary["contexts_updated"] += 1
            context.canonical_player_id = canonical_player_id
            context.full_name = full_name
            context.normalized_name = normalize_player_name(full_name)
            context.position = position
            context.team = team
            context.age = _safe_int(player.get("age"))
            context.birth_date = _safe_str(player.get("birth_date"))
            context.years_exp = _safe_int(player.get("years_exp"))
            context.entry_year = _safe_int(player.get("entry_year"))
            context.rookie_year = _safe_int(player.get("rookie_year"))
            context.injury_status = _safe_str(player.get("injury_status"))
            context.status = _safe_str(player.get("status"))
            context.depth_chart_position = _safe_str(player.get("depth_chart_position"))
            context.raw_data = json.dumps(player, sort_keys=True)
            context.updated_at = utc_now()

        db.commit()
        return summary
    except Exception:
        db.rollback()
        raise
    finally:
        if owns_db:
            db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh Sleeper current player context")
    parser.add_argument("--season", type=int, required=True, help="Fantasy/NFL season for the context snapshot")
    args = parser.parse_args()
    summary = refresh_sleeper_context(season=args.season)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
