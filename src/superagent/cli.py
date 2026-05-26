"""
CLI formatting and display helpers for Superagent.

Converts agent/tool output into readable CLI output: tables, formatted text, summaries.
"""

from typing import Any, Dict, List
from tabulate import tabulate


def format_team_summary(data: Dict[str, Any]) -> str:
    """Format team summary data as a readable table."""
    if not data:
        return "No data available."

    lines = []
    lines.append(f"\n{'='*70}")
    lines.append(f"Team: {data.get('team', 'N/A')} ({data.get('season', 'N/A')})")
    lines.append(f"{'='*70}\n")

    # Record and scoring
    record_section = [
        [f"Record", f"{data.get('wins', 0)}-{data.get('losses', 0)}"],
        [f"Games", data.get('games', 0)],
        [f"Points For", data.get('points_for', 0)],
        [f"Points Against", data.get('points_against', 0)],
        [f"Point Diff", data.get('points_for', 0) - data.get('points_against', 0)],
    ]
    lines.append(tabulate(record_section, headers=["Metric", "Value"], tablefmt="plain"))

    # Offensive stats
    lines.append("\n📊 Offensive Stats")
    lines.append("-" * 70)
    off_section = [
        ["Total EPA", f"{data.get('offensive_epa', 0):.2f}"],
        ["EPA/Play", f"{data.get('offensive_epa_per_play', 0):.4f}"],
        ["Avg Yards/Game", f"{data.get('avg_offensive_yards', 0):.1f}"],
        ["Total Plays", data.get('play_count', 0)],
    ]
    lines.append(tabulate(off_section, headers=["Metric", "Value"], tablefmt="plain"))

    # Defensive stats
    lines.append("\n🛡️  Defensive Stats")
    lines.append("-" * 70)
    def_section = [
        ["Total EPA Allowed", f"{data.get('defensive_epa_allowed', 0):.2f}"],
        ["EPA/Play Allowed", f"{data.get('defensive_epa_per_play_allowed', 0):.4f}"],
    ]
    lines.append(tabulate(def_section, headers=["Metric", "Value"], tablefmt="plain"))

    lines.append("\n" + "="*70 + "\n")
    return "\n".join(lines)


def format_player_summary(data: Dict[str, Any]) -> str:
    """Format player summary data as a readable table."""
    if not data:
        return "No data available."

    lines = []
    lines.append(f"\n{'='*70}")
    lines.append(f"Player: {data.get('name', 'N/A')} ({data.get('position', 'N/A')})")
    lines.append(f"Team: {data.get('team', 'N/A')}")
    lines.append(f"{'='*70}\n")

    # Basic info
    basic_section = [
        ["Games Played", data.get('games', 0)],
    ]
    lines.append(tabulate(basic_section, headers=["Metric", "Value"], tablefmt="plain"))

    # Passing stats (if applicable)
    if data.get('passing_attempts', 0) > 0:
        lines.append("\n📤 Passing Stats")
        lines.append("-" * 70)
        pass_section = [
            ["Attempts", data.get('passing_attempts', 0)],
            ["Completions", data.get('completions', 0)],
            ["Completion %", f"{data.get('completion_pct', 0):.1%}"],
            ["Passing Yards", data.get('passing_yards', 0)],
            ["Passing TDs", data.get('passing_tds', 0)],
            ["Interceptions", data.get('interceptions', 0)],
        ]
        lines.append(tabulate(pass_section, headers=["Metric", "Value"], tablefmt="plain"))

    # Rushing stats (if applicable)
    if data.get('carries', 0) > 0:
        lines.append("\n🏃 Rushing Stats")
        lines.append("-" * 70)
        rush_section = [
            ["Carries", data.get('carries', 0)],
            ["Rushing Yards", data.get('rushing_yards', 0)],
            ["Rushing TDs", data.get('rushing_tds', 0)],
        ]
        lines.append(tabulate(rush_section, headers=["Metric", "Value"], tablefmt="plain"))

    # Receiving stats (if applicable)
    if data.get('targets', 0) > 0:
        lines.append("\n👐 Receiving Stats")
        lines.append("-" * 70)
        rec_section = [
            ["Targets", data.get('targets', 0)],
            ["Receptions", data.get('receptions', 0)],
            ["Receiving Yards", data.get('receiving_yards', 0)],
            ["Receiving TDs", data.get('receiving_tds', 0)],
        ]
        lines.append(tabulate(rec_section, headers=["Metric", "Value"], tablefmt="plain"))

    lines.append("\n" + "="*70 + "\n")
    return "\n".join(lines)


def format_player_comparison(data: List[Dict[str, Any]]) -> str:
    """Format player comparison data as a side-by-side table."""
    if not data:
        return "No data available."

    # Build table rows
    rows = []
    headers = ["Metric"]

    # Collect all player names and prepare headers
    for player in data:
        if "error" not in player:
            headers.append(player.get("name", "Unknown"))

    # Collect all possible metrics (keys from successful players)
    all_metrics = set()
    for player in data:
        if "error" not in player:
            all_metrics.update(player.keys())

    # Remove display fields from metrics
    skip_fields = {"player_id", "name", "position", "team"}
    all_metrics = sorted(all_metrics - skip_fields)

    # Build rows for each metric
    for metric in all_metrics:
        row = [metric.replace("_", " ").title()]
        for player in data:
            if "error" in player:
                row.append("N/A")
            else:
                value = player.get(metric, "N/A")
                if isinstance(value, float):
                    row.append(f"{value:.4f}")
                else:
                    row.append(str(value))
        rows.append(row)

    lines = []
    lines.append(f"\n{'='*70}")
    lines.append("Player Comparison")
    lines.append(f"{'='*70}\n")
    lines.append(tabulate(rows, headers=headers, tablefmt="grid"))
    lines.append("\n" + "="*70 + "\n")

    return "\n".join(lines)


def format_epa_trend(data: List[Dict[str, Any]]) -> str:
    """Format EPA trend data as a table."""
    if not data:
        return "No data available."

    lines = []
    lines.append(f"\n{'='*70}")
    lines.append("Weekly EPA Trend")
    lines.append(f"{'='*70}\n")

    rows = []
    for week_data in data:
        rows.append([
            f"Week {week_data.get('week', 'N/A')}",
            f"{week_data.get('offensive_epa', 0):.2f}",
            f"{week_data.get('defensive_epa_allowed', 0):.2f}",
            f"{week_data.get('net_epa', 0):.2f}",
            week_data.get('play_count', 0),
        ])

    lines.append(tabulate(
        rows,
        headers=["Week", "Off EPA", "Def EPA", "Net EPA", "Plays"],
        tablefmt="grid"
    ))

    lines.append("\n" + "="*70 + "\n")
    return "\n".join(lines)


def format_agent_response(result: Dict[str, Any]) -> str:
    """Format agent response for CLI display."""
    lines = []

    if not result.get("ok"):
        lines.append(f"❌ Error: {result.get('error', 'Unknown error')}")
        return "\n".join(lines)

    # Main answer
    answer = result.get("answer", "").strip()
    if answer:
        lines.append(answer)

    # Tools used summary
    tools_used = result.get("tools_used", [])
    if tools_used:
        lines.append("\n📊 Tools Used:")
        for tool in tools_used:
            name = tool.get("name", "unknown")
            ok = tool.get("result", {}).get("ok", False)
            status = "✅" if ok else "❌"
            lines.append(f"  {status} {name}")

    return "\n".join(lines)


def print_welcome():
    """Print welcome banner."""
    print("\n" + "="*70)
    print("🏈 Superagent v1.0 — NFL Intelligence Platform")
    print("="*70)
    print("\nAsk questions about NFL stats, teams, players, and trends.")
    print("Type 'help' for examples, 'exit' to quit.\n")


def print_help():
    """Print help with example questions."""
    print("\n" + "="*70)
    print("Example Questions:")
    print("="*70)
    examples = [
        "Get Josh Allen's fantasy stats for 2024 in PPR.",
        "What was Josh Allen's EPA per play in 2024?",
        "Compare Josh Allen and Lamar Jackson by EPA and CPOE in 2024.",
        "Compare Josh Allen and Lamar Jackson in 2024.",
        "Compare James Cook and Khalil Shakir in half-PPR for 2024.",
        "Show James Cook's weekly usage in 2024.",
        "Find RB usage risers from weeks 1-17 in 2024.",
        "Which WRs had 100+ targets in 2024?",
        "Find late-season RB breakouts in 2024.",
        "When are the Bills on bye in 2026?",
        "Show the Bills schedule for 2025.",
        "Who do the Bills play from Week 10 on in 2025?",
        "List all NFL bye weeks in 2026.",
        "How did the Bills offense perform in weeks 1-5 of 2024?",
        "What was the Bills' record in 2023?",
        "Get the Cowboys' defensive EPA trend for weeks 10-17 in 2024.",
    ]
    for example in examples:
        print(f"  • {example}")
    print("\nType 'exit' to quit.\n")
