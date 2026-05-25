"""
League-specific draft value adjustments.

This module intentionally stays modest in Phase 10C. It does not make draft
recommendations; it translates base market value into league-context value
signals for Phase 10D tools.
"""

from __future__ import annotations

from typing import Any

from superagent.models import DraftPlayerMarket, LeagueSettings


PPR_VALUES = {
    "standard": 0.0,
    "half_ppr": 0.5,
    "half": 0.5,
    "ppr": 1.0,
    "full_ppr": 1.0,
    "full": 1.0,
}


def normalize_ppr_type(ppr_type: str | None) -> str:
    """Normalize user-facing PPR labels."""
    if not ppr_type:
        return "ppr"
    normalized = ppr_type.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in {"standard", "half_ppr", "ppr"}:
        return normalized
    if normalized == "half":
        return "half_ppr"
    if normalized in {"full", "full_ppr"}:
        return "ppr"
    return normalized


def ppr_points_per_reception(ppr_type: str | None) -> float:
    """Return points per reception for a scoring type."""
    return PPR_VALUES.get(normalize_ppr_type(ppr_type), 1.0)


def _base_value(market: DraftPlayerMarket) -> float:
    if market.value is not None:
        return float(market.value)
    if market.ecr is not None and market.adp is not None:
        return float(market.adp) - float(market.ecr)
    if market.avg_rank is not None:
        return max(0.0, 250.0 - float(market.avg_rank)) / 10.0
    return 0.0


def _position_adjustment(position: str | None, settings: LeagueSettings) -> float:
    position = (position or "").upper()
    adjustment = 0.0

    receptions = ppr_points_per_reception(settings.ppr_type)
    if position in {"WR", "TE"}:
        adjustment += receptions * 6.0
    elif position == "RB":
        adjustment += receptions * 3.0

    if position == "QB":
        adjustment += float(settings.superflex_slots or 0) * 22.0
        passing_td_points = 4.0 if settings.passing_td_points is None else float(settings.passing_td_points)
        adjustment += max(0.0, passing_td_points - 4.0) * 3.5

    if position == "TE" and settings.te_slots > 1:
        adjustment += 5.0

    if position in {"RB", "WR", "TE"}:
        adjustment += float(settings.flex_slots or 0) * 1.5
    return adjustment


def adjust_draft_value(
    market: DraftPlayerMarket,
    settings: LeagueSettings,
) -> dict[str, Any]:
    """
    Return league-context draft value for one market row.

    The output is machine-friendly and intentionally transparent so 10D can use
    it as one input among ADP, roster need, and already-drafted players.
    """
    base_value = _base_value(market)
    adjustment = _position_adjustment(market.position, settings)
    adjusted_value = round(base_value + adjustment, 3)

    return {
        "canonical_player_id": market.canonical_player_id,
        "source_player_name": market.source_player_name,
        "position": market.position,
        "base_value": round(base_value, 3),
        "league_adjustment": round(adjustment, 3),
        "adjusted_value": adjusted_value,
        "settings": {
            "ppr_type": normalize_ppr_type(settings.ppr_type),
            "superflex_slots": settings.superflex_slots,
            "passing_td_points": settings.passing_td_points,
            "flex_slots": settings.flex_slots,
        },
    }
