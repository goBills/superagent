"""
Canonical player identity and source mapping helpers.

Canonical identity lives in the product database because external draft sources,
league settings, and user review state are product data. DuckDB remains the
historical analytics warehouse.
"""

from __future__ import annotations

import json
import re
from typing import Any

import duckdb
from rapidfuzz import fuzz
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from superagent.config import get_config
from superagent.db import SessionLocal
from superagent.models import (
    CanonicalPlayer,
    CanonicalPlayerAlias,
    DraftImportReview,
    ExternalPlayerMapping,
    PlayerSeason,
)


AUTO_CONFIDENCE_THRESHOLD = 0.85
REVIEW_CONFIDENCE_THRESHOLD = 0.65


def normalize_player_name(name: str | None) -> str:
    """Normalize player names for matching across source quirks."""
    if not name:
        return ""
    normalized = name.lower()
    normalized = normalized.replace(".", "")
    normalized = normalized.replace("'", "")
    normalized = normalized.replace("’", "")
    normalized = normalized.replace("-", " ")
    normalized = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", normalized)
    normalized = re.sub(r"[^a-z0-9]+", "", normalized)
    return normalized.strip()


def canonical_id_from_nflverse(player_id: str, full_name: str) -> str:
    """Create a stable canonical id from nflverse's player id."""
    normalized_id = re.sub(r"[^a-z0-9]+", "_", str(player_id).lower()).strip("_")
    if normalized_id:
        return f"nfl_{normalized_id}"
    fallback = normalize_player_name(full_name) or "unknown"
    return f"nfl_{fallback}"


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _standard_response(ok: bool, **kwargs: Any) -> dict[str, Any]:
    payload = {"ok": ok, "error": None}
    payload.update(kwargs)
    if not ok and payload.get("error") is None:
        payload["error"] = "Unknown error"
    return payload


def _season_context(
    db: Session,
    canonical_player_id: str,
    season: int,
    position: str | None = None,
) -> PlayerSeason | None:
    query = db.query(PlayerSeason).filter(
        PlayerSeason.canonical_player_id == canonical_player_id,
        PlayerSeason.season == season,
    )
    if position:
        query = query.filter(func.upper(PlayerSeason.position) == position.upper())
    return (
        query.order_by(
            PlayerSeason.team.is_(None),
            PlayerSeason.position.is_(None),
            PlayerSeason.id,
        )
        .first()
    )


def _candidate_payload(
    db: Session,
    player: CanonicalPlayer,
    season: int,
    score: float,
    source: str,
    position: str | None = None,
) -> dict[str, Any]:
    season_info = _season_context(db, player.canonical_player_id, season, position)
    fallback_season = None
    if season_info is None:
        fallback_season = (
            db.query(PlayerSeason)
            .filter(PlayerSeason.canonical_player_id == player.canonical_player_id)
            .order_by(PlayerSeason.season.desc(), PlayerSeason.id.desc())
            .first()
        )

    context = season_info or fallback_season
    return {
        "canonical_player_id": player.canonical_player_id,
        "nflverse_player_id": player.nflverse_player_id,
        "full_name": player.full_name,
        "season": season,
        "team": context.team if context else None,
        "position": context.position if context else None,
        "confidence": round(float(score), 3),
        "source": source,
    }


def _resolve_candidates(
    db: Session,
    name: str,
    season: int,
    position: str | None = None,
) -> list[dict[str, Any]]:
    normalized = normalize_player_name(name)
    if not normalized:
        return []

    exact_aliases = (
        db.query(CanonicalPlayerAlias)
        .filter(CanonicalPlayerAlias.normalized_alias == normalized)
        .all()
    )
    if exact_aliases:
        candidates = []
        seen = set()
        for alias in exact_aliases:
            player = alias.canonical_player
            if player.canonical_player_id in seen:
                continue
            if position and not _season_context(db, player.canonical_player_id, season, position):
                continue
            seen.add(player.canonical_player_id)
            candidates.append(_candidate_payload(db, player, season, 1.0, "exact_alias", position))
        return candidates

    aliases = (
        db.query(CanonicalPlayerAlias)
        .join(CanonicalPlayer)
        .all()
    )
    best_by_player: dict[str, dict[str, Any]] = {}
    for alias in aliases:
        player = alias.canonical_player
        name_score = max(
            fuzz.ratio(normalized, alias.normalized_alias) / 100.0,
            fuzz.token_set_ratio(name, alias.alias) / 100.0,
        )
        if name_score < 0.70:
            continue

        season_info = _season_context(db, player.canonical_player_id, season)
        if season_info:
            name_score += 0.03
        if position:
            if season_info and season_info.position and season_info.position.upper() == position.upper():
                name_score += 0.08
            else:
                name_score -= 0.10
        score = min(max(name_score, 0.0), 1.0)

        candidate = _candidate_payload(db, player, season, score, "fuzzy_alias", position)
        existing = best_by_player.get(player.canonical_player_id)
        if existing is None or candidate["confidence"] > existing["confidence"]:
            best_by_player[player.canonical_player_id] = candidate

    return sorted(
        best_by_player.values(),
        key=lambda candidate: (
            candidate["confidence"],
            candidate.get("position") == position if position else False,
            candidate.get("full_name") or "",
        ),
        reverse=True,
    )


def resolve_to_canonical(
    name: str,
    season: int,
    position: str | None = None,
    db: Session | None = None,
) -> dict[str, Any]:
    """
    Resolve an arbitrary player name to a canonical player.

    Ambiguous high-confidence names return candidates instead of guessing.
    """
    owns_session = db is None
    db = db or SessionLocal()
    try:
        candidates = _resolve_candidates(db, name, season, position)
        if not candidates:
            return _standard_response(False, error=f"No canonical player candidates found for '{name}'")

        best = candidates[0]
        tied = [
            candidate
            for candidate in candidates
            if abs(candidate["confidence"] - best["confidence"]) < 0.02
        ]
        if len(tied) > 1 and not position:
            return _standard_response(
                False,
                error=f"Ambiguous player name '{name}'",
                needs_review=True,
                candidates=candidates[:5],
            )

        if best["confidence"] >= AUTO_CONFIDENCE_THRESHOLD:
            return _standard_response(True, **best, candidates=candidates[:5])

        return _standard_response(
            False,
            error=f"Low-confidence canonical match for '{name}'",
            needs_review=True,
            candidates=candidates[:5],
        )
    finally:
        if owns_session:
            db.close()


def auto_map_external_player(
    source: str,
    season: int,
    source_player_name: str,
    source_player_id: str | None = None,
    position: str | None = None,
    db: Session | None = None,
) -> dict[str, Any]:
    """Map a source player row to canonical identity or queue it for review."""
    owns_session = db is None
    db = db or SessionLocal()
    try:
        resolution = resolve_to_canonical(source_player_name, season, position=position, db=db)
        if resolution["ok"]:
            mapping = (
                db.query(ExternalPlayerMapping)
                .filter(
                    ExternalPlayerMapping.source == source,
                    ExternalPlayerMapping.season == season,
                    ExternalPlayerMapping.source_player_name == source_player_name,
                    ExternalPlayerMapping.source_player_id == source_player_id,
                )
                .first()
            )
            if mapping is None:
                mapping = ExternalPlayerMapping(
                    source=source,
                    season=season,
                    source_player_name=source_player_name,
                    source_player_id=source_player_id,
                )
                db.add(mapping)
            mapping.canonical_player_id = resolution["canonical_player_id"]
            mapping.confidence = resolution["confidence"]
            mapping.status = "auto"
            db.commit()
            return _standard_response(
                True,
                canonical_player_id=resolution["canonical_player_id"],
                confidence=resolution["confidence"],
                status="auto",
            )

        candidates = resolution.get("candidates", [])
        review = DraftImportReview(
            source=source,
            season=season,
            source_player_name=source_player_name,
            source_player_id=source_player_id,
            candidates=json.dumps(candidates),
            status="pending",
        )
        db.add(review)
        db.commit()
        return _standard_response(
            False,
            error="needs_review",
            needs_review=True,
            candidates=candidates,
            review_id=review.id,
        )
    finally:
        if owns_session:
            db.close()


def _upsert_alias(
    db: Session,
    canonical_player_id: str,
    alias: str | None,
    source: str,
) -> None:
    alias = _safe_str(alias)
    normalized_alias = normalize_player_name(alias)
    if not alias or not normalized_alias:
        return

    exists = (
        db.query(CanonicalPlayerAlias)
        .filter(
            CanonicalPlayerAlias.canonical_player_id == canonical_player_id,
            CanonicalPlayerAlias.normalized_alias == normalized_alias,
            CanonicalPlayerAlias.source == source,
        )
        .first()
    )
    if exists:
        return
    db.add(
        CanonicalPlayerAlias(
            canonical_player_id=canonical_player_id,
            alias=alias,
            normalized_alias=normalized_alias,
            source=source,
        )
    )


def _upsert_player_season(
    db: Session,
    canonical_player_id: str,
    season: int,
    team: str | None,
    position: str | None,
    age: int | None,
) -> bool:
    exists = (
        db.query(PlayerSeason)
        .filter(
            PlayerSeason.canonical_player_id == canonical_player_id,
            PlayerSeason.season == season,
            PlayerSeason.team == team,
            PlayerSeason.position == position,
        )
        .first()
    )
    if exists:
        if age and not exists.age:
            exists.age = age
        return False

    db.add(
        PlayerSeason(
            canonical_player_id=canonical_player_id,
            season=season,
            team=team,
            position=position,
            age=age,
        )
    )
    return True


def seed_canonical_players_from_nflverse(
    seasons: list[int] | None = None,
    db: Session | None = None,
    duckdb_path: str | None = None,
) -> dict[str, int]:
    """
    Seed product DB canonical identity from existing DuckDB nflverse tables.

    Roster rows are ground truth because they include rookies, backups, and
    handcuffs who may not have plays yet. Weekly and play-by-play names enrich
    aliases when available.
    """
    owns_session = db is None
    db = db or SessionLocal()
    config = get_config()
    seasons = seasons or config.NFL_SEASONS
    summary = {
        "players_created": 0,
        "players_seen": 0,
        "player_seasons_created": 0,
        "aliases_created": 0,
    }

    conn = duckdb.connect(duckdb_path or str(config.DATABASE_PATH))
    try:
        season_params = ",".join(["?"] * len(seasons))
        roster_rows = conn.execute(
            f"""
            SELECT DISTINCT
                season,
                gsis_id,
                full_name,
                football_name,
                team,
                position,
                age
            FROM rosters
            WHERE season IN ({season_params})
              AND gsis_id IS NOT NULL
              AND full_name IS NOT NULL
            """,
            seasons,
        ).fetchall()

        before_aliases = db.query(CanonicalPlayerAlias).count()
        for season, player_id, full_name, football_name, team, position, age in roster_rows:
            player_id = str(player_id)
            canonical_player_id = canonical_id_from_nflverse(player_id, str(full_name))
            player = db.query(CanonicalPlayer).filter(
                or_(
                    CanonicalPlayer.canonical_player_id == canonical_player_id,
                    CanonicalPlayer.nflverse_player_id == player_id,
                )
            ).first()
            if player is None:
                player = CanonicalPlayer(
                    canonical_player_id=canonical_player_id,
                    nflverse_player_id=player_id,
                    full_name=str(full_name),
                    normalized_name=normalize_player_name(str(full_name)),
                )
                db.add(player)
                summary["players_created"] += 1
            summary["players_seen"] += 1

            if _upsert_player_season(
                db,
                canonical_player_id,
                int(season),
                _safe_str(team),
                _safe_str(position),
                _as_int(age),
            ):
                summary["player_seasons_created"] += 1
            _upsert_alias(db, canonical_player_id, str(full_name), "nflverse_rosters")
            _upsert_alias(db, canonical_player_id, football_name, "nflverse_rosters")

        db.commit()

        weekly_rows = conn.execute(
            f"""
            SELECT DISTINCT player_id, player_display_name, player_name
            FROM weekly
            WHERE season IN ({season_params})
              AND player_id IS NOT NULL
            """,
            seasons,
        ).fetchall()
        for player_id, display_name, player_name in weekly_rows:
            player = db.query(CanonicalPlayer).filter(
                CanonicalPlayer.nflverse_player_id == str(player_id)
            ).first()
            if player:
                _upsert_alias(db, player.canonical_player_id, display_name, "nflverse_weekly")
                _upsert_alias(db, player.canonical_player_id, player_name, "nflverse_weekly")

        play_name_columns = [
            ("passer_player_id", "passer_player_name"),
            ("rusher_player_id", "rusher_player_name"),
            ("receiver_player_id", "receiver_player_name"),
        ]
        for id_column, name_column in play_name_columns:
            rows = conn.execute(
                f"""
                SELECT DISTINCT {id_column}, {name_column}
                FROM plays
                WHERE season IN ({season_params})
                  AND {id_column} IS NOT NULL
                  AND {name_column} IS NOT NULL
                """,
                seasons,
            ).fetchall()
            for player_id, alias in rows:
                player = db.query(CanonicalPlayer).filter(
                    CanonicalPlayer.nflverse_player_id == str(player_id)
                ).first()
                if player:
                    _upsert_alias(db, player.canonical_player_id, alias, "nflverse_pbp")

        db.commit()
        after_aliases = db.query(CanonicalPlayerAlias).count()
        summary["aliases_created"] = max(after_aliases - before_aliases, 0)
        return summary
    finally:
        conn.close()
        if owns_session:
            db.close()
