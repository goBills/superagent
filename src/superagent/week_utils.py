"""Utilities for NFL week handling and playoff round naming."""


def get_week_label(week: int) -> str:
    """
    Convert NFL week number to human-readable label.

    Regular season: 1-17 (or 1-16 for pre-2021)
    Playoffs: 18=Wild Card, 19=Divisional, 20=Conference Championship, 21=Super Bowl

    Args:
        week: Week number (1-based)

    Returns:
        Human-readable week/round label (e.g., "Week 14" or "Divisional Round")
    """
    if week is None:
        return "Unknown"

    week = int(week)

    # Regular season (1-17)
    if 1 <= week <= 17:
        return f"Week {week}"

    # Playoff weeks
    playoff_map = {
        18: "Wild Card Round",
        19: "Divisional Round",
        20: "Conference Championship",
        21: "Super Bowl",
    }

    return playoff_map.get(week, f"Week {week}")


def is_playoff_week(week: int) -> bool:
    """Check if week number is a playoff week."""
    return week in [18, 19, 20, 21]


def week_range_label(start_week: int, end_week: int) -> str:
    """
    Create a readable label for a week range.

    Args:
        start_week: Starting week
        end_week: Ending week

    Returns:
        Readable range label (e.g., "Weeks 1-17" or "Regular Season through Divisional Round")
    """
    start_label = get_week_label(start_week)
    end_label = get_week_label(end_week)

    if start_week == end_week:
        return start_label

    # If both regular season, just use week numbers
    if start_week <= 17 and end_week <= 17:
        return f"Weeks {start_week}-{end_week}"

    # If spans regular season and playoffs
    if start_week <= 17 < end_week:
        return f"{start_label} through {end_label}"

    # If both playoff
    if start_week >= 18 and end_week >= 18:
        return f"{start_label} through {end_label}"

    return f"{start_label} through {end_label}"
