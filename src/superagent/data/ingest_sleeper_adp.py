"""Import Sleeper season-long ADP into the source-agnostic draft market.

Sleeper's public players API remains the identity source; this importer uses the
companion projections surface for ADP-like draft ranks and writes normal
DraftPlayerMarket rows for a season/source.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from typing import Any

import requests
from sqlalchemy.orm import Session

from superagent.data.refresh_sleeper_context import (
    _ensure_sleeper_canonical,
    _normalize_sleeper_position,
    _safe_int,
    _safe_str,
    _upsert_external_mapping,
)
from superagent.db import SessionLocal
from superagent.models import DraftMarketImport, DraftPlayerMarket, DraftSourceRank, ExternalPlayerMapping


SLEEPER_ADP_SOURCE = "sleeper_adp"
SLEEPER_PROJECTIONS_URL = "https://api.sleeper.com/projections/nfl/{season}"
ADP_STAT_BY_SCORING = {
    "ppr": "adp_ppr",
    "half_ppr": "adp_half_ppr",
    "std": "adp_std",
    "2qb": "adp_2qb",
}
SOURCE_RANK_LABELS = {
    "adp_ppr": "Sleeper PPR ADP",
    "adp_half_ppr": "Sleeper Half PPR ADP",
    "adp_std": "Sleeper Standard ADP",
    "adp_2qb": "Sleeper 2QB ADP",
    "adp_dynasty": "Sleeper Dynasty ADP",
    "adp_dynasty_ppr": "Sleeper Dynasty PPR ADP",
    "adp_dynasty_half_ppr": "Sleeper Dynasty Half PPR ADP",
    "adp_dynasty_std": "Sleeper Dynasty Standard ADP",
    "adp_dynasty_2qb": "Sleeper Dynasty 2QB ADP",
}
FANTASY_MARKET_POSITIONS = {"QB", "RB", "WR", "TE", "K", "DST"}


class SleeperAdpIngestionError(ValueError):
    """Raised when Sleeper ADP ingestion cannot safely complete."""


def _fetch_sleeper_projections(season: int) -> list[dict[str, Any]]:
    response = requests.get(
        SLEEPER_PROJECTIONS_URL.format(season=season),
        params={"season_type": "regular"},
        timeout=45,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        raise SleeperAdpIngestionError("Sleeper projections response was not a list")
    return data


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed


def _valid_adp(value: Any, max_adp: float) -> float | None:
    parsed = _safe_float(value)
    if parsed is None or parsed <= 0 or parsed >= 999 or parsed > max_adp:
        return None
    return parsed


def _full_name(row: dict[str, Any]) -> str | None:
    player = row.get("player") or {}
    return _safe_str(player.get("full_name")) or " ".join(
        part for part in [_safe_str(player.get("first_name")), _safe_str(player.get("last_name"))] if part
    )


def _row_team(row: dict[str, Any]) -> str | None:
    player = row.get("player") or {}
    return _safe_str(player.get("team")) or _safe_str(player.get("team_abbr")) or _safe_str(row.get("team"))


def _row_position(row: dict[str, Any]) -> str | None:
    player = row.get("player") or {}
    return _normalize_sleeper_position(_safe_str(player.get("position")) or _safe_str(row.get("position")))


def _source_ranks(stats: dict[str, Any]) -> dict[str, float]:
    ranks = {}
    for stat, label in SOURCE_RANK_LABELS.items():
        value = _valid_adp(stats.get(stat), max_adp=998)
        if value is not None:
            ranks[label] = value
    return ranks


def _canonical_from_sleeper_mapping(
    db: Session,
    season: int,
    player_id: str,
    full_name: str,
) -> str | None:
    mapping = (
        db.query(ExternalPlayerMapping)
        .filter(
            ExternalPlayerMapping.source == "sleeper",
            ExternalPlayerMapping.season == season,
            ExternalPlayerMapping.source_player_name == full_name,
            ExternalPlayerMapping.source_player_id == player_id,
            ExternalPlayerMapping.status == "approved",
        )
        .first()
    )
    return mapping.canonical_player_id if mapping else None


def _clear_source_season(db: Session, source: str, season: int) -> dict[str, int]:
    imports = (
        db.query(DraftMarketImport)
        .filter(DraftMarketImport.source == source, DraftMarketImport.season == season)
        .all()
    )
    market_count = (
        db.query(DraftPlayerMarket)
        .filter(DraftPlayerMarket.source == source, DraftPlayerMarket.season == season)
        .count()
    )
    for import_batch in imports:
        db.delete(import_batch)
    db.flush()
    return {"imports_deleted": len(imports), "markets_deleted": int(market_count)}


def _upsert_source_rank(db: Session, market: DraftPlayerMarket, rank_source: str, rank_value: float) -> None:
    source_rank = (
        db.query(DraftSourceRank)
        .filter(DraftSourceRank.market_id == market.id, DraftSourceRank.rank_source == rank_source)
        .first()
    )
    if source_rank is None:
        db.add(DraftSourceRank(market_id=market.id, rank_source=rank_source, rank_value=rank_value))
    else:
        source_rank.rank_value = rank_value


def ingest_sleeper_adp(
    *,
    season: int,
    scoring: str = "ppr",
    source: str = SLEEPER_ADP_SOURCE,
    projections: list[dict[str, Any]] | None = None,
    db: Session | None = None,
    replace: bool = True,
    min_import_rows: int = 150,
    max_adp: float = 350,
) -> dict[str, Any]:
    """Import Sleeper ADP rows into DraftPlayerMarket."""
    if season < 2020 or season > 2035:
        raise SleeperAdpIngestionError(f"Invalid season: {season}")
    scoring = scoring.strip().lower()
    if scoring not in ADP_STAT_BY_SCORING:
        raise SleeperAdpIngestionError(f"Unsupported scoring '{scoring}'. Use one of {sorted(ADP_STAT_BY_SCORING)}")
    if not source.strip():
        raise SleeperAdpIngestionError("Source is required")
    min_import_rows = max(1, int(min_import_rows or 1))
    max_adp = max(1, float(max_adp or 350))

    rows = projections if projections is not None else _fetch_sleeper_projections(season)
    adp_stat = ADP_STAT_BY_SCORING[scoring]

    owns_db = db is None
    db = db or SessionLocal()
    try:
        cleared = {"imports_deleted": 0, "markets_deleted": 0}
        if replace:
            cleared = _clear_source_season(db, source, season)
        else:
            existing = (
                db.query(DraftMarketImport)
                .filter(
                    DraftMarketImport.source == source,
                    DraftMarketImport.season == season,
                    DraftMarketImport.file_name == f"sleeper-adp-{season}-{scoring}.json",
                )
                .first()
            )
            if existing:
                db.delete(existing)
                db.flush()

        import_batch = DraftMarketImport(
            source=source,
            season=season,
            file_name=f"sleeper-adp-{season}-{scoring}.json",
            sheet_name=scoring,
            status="completed",
            rows_seen=len(rows),
        )
        db.add(import_batch)
        db.flush()

        prepared: list[dict[str, Any]] = []
        skipped_no_adp = 0
        skipped_position = 0
        canonical_created = 0
        mapped_from_existing_sleeper_mapping = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            stats = row.get("stats") or {}
            if not isinstance(stats, dict):
                continue
            adp = _valid_adp(stats.get(adp_stat), max_adp=max_adp)
            if adp is None:
                skipped_no_adp += 1
                continue

            player = row.get("player") or {}
            player_id = _safe_str(row.get("player_id"))
            full_name = _full_name(row)
            position = _row_position(row)
            team = _row_team(row)
            if not player_id or not full_name:
                skipped_no_adp += 1
                continue
            if position not in FANTASY_MARKET_POSITIONS:
                skipped_position += 1
                continue

            canonical_player_id = _canonical_from_sleeper_mapping(db, season, player_id, full_name)
            if canonical_player_id:
                mapped_from_existing_sleeper_mapping += 1
            else:
                canonical_player_id = _ensure_sleeper_canonical(
                    db,
                    player_id=player_id,
                    full_name=full_name,
                    position=position,
                    season=season,
                    team=team,
                    age=_safe_int(player.get("age")),
                    birth_date=_safe_str(player.get("birth_date")),
                )
                _upsert_external_mapping(
                    db,
                    season=season,
                    source_player_id=player_id,
                    source_player_name=full_name,
                    canonical_player_id=canonical_player_id,
                    confidence=0.72,
                    status="approved",
                )
                canonical_created += 1

            prepared.append(
                {
                    "row": row,
                    "stats": stats,
                    "canonical_player_id": canonical_player_id,
                    "full_name": full_name,
                    "position": position,
                    "team": team,
                    "adp": adp,
                    "source_ranks": _source_ranks(stats),
                }
            )

        if len(prepared) < min_import_rows:
            raise SleeperAdpIngestionError(
                f"Sleeper ADP import refused: only {len(prepared)} rows mapped, below minimum {min_import_rows}"
            )

        prepared.sort(key=lambda item: (item["adp"], item["full_name"]))
        position_counts: dict[str, int] = defaultdict(int)
        market_cache = {
            market.canonical_player_id: market
            for market in db.query(DraftPlayerMarket)
            .filter(DraftPlayerMarket.source == source, DraftPlayerMarket.season == season)
            .all()
        }
        for item in prepared:
            position_counts[item["position"]] += 1
            market = market_cache.get(item["canonical_player_id"])
            if market is None:
                market = DraftPlayerMarket(
                    import_id=import_batch.id,
                    source=source,
                    season=season,
                    canonical_player_id=item["canonical_player_id"],
                    source_player_name=item["full_name"],
                )
                db.add(market)
                db.flush()
                market_cache[item["canonical_player_id"]] = market
            market.import_id = import_batch.id
            market.source_player_name = item["full_name"]
            market.team = item["team"]
            market.position = item["position"]
            market.position_rank = position_counts[item["position"]]
            market.overall_rank = item["adp"]
            market.adp = item["adp"]
            market.avg_rank = item["adp"]
            market.ecr = None
            market.raw_data = json.dumps(item["row"], sort_keys=True)
            for rank_source, rank_value in item["source_ranks"].items():
                _upsert_source_rank(db, market, rank_source, rank_value)

        import_batch.rows_imported = len(prepared)
        import_batch.rows_needing_review = 0
        db.commit()
        return {
            "ok": True,
            "source": source,
            "season": season,
            "scoring": scoring,
            "adp_stat": adp_stat,
            "replace": replace,
            "replace_deleted": cleared if replace else None,
            "rows_seen": len(rows),
            "rows_imported": len(prepared),
            "skipped_no_adp": skipped_no_adp,
            "skipped_position": skipped_position,
            "canonical_created": canonical_created,
            "mapped_from_existing_sleeper_mapping": mapped_from_existing_sleeper_mapping,
            "max_adp": max_adp,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        if owns_db:
            db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Sleeper ADP into draft market rows")
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--scoring", choices=sorted(ADP_STAT_BY_SCORING), default="ppr")
    parser.add_argument("--source", default=SLEEPER_ADP_SOURCE)
    parser.add_argument("--max-adp", type=float, default=350)
    parser.add_argument("--min-import-rows", type=int, default=150)
    parser.add_argument("--no-replace", action="store_true")
    args = parser.parse_args()
    summary = ingest_sleeper_adp(
        season=args.season,
        scoring=args.scoring,
        source=args.source,
        max_adp=args.max_adp,
        min_import_rows=args.min_import_rows,
        replace=not args.no_replace,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
