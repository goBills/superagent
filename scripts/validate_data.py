"""
Data validation script for Superagent.

Runs sanity checks on the DuckDB database to ensure data loaded correctly.
"""

import sys
from pathlib import Path
import duckdb
from rich.console import Console
from rich.table import Table

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from superagent.config import get_config

console = Console()
config = get_config()


def validate_database():
    """Run validation checks on the database."""
    console.print("\n" + "=" * 80)
    console.print("[bold cyan]Superagent: Data Validation[/bold cyan]")
    console.print("=" * 80)

    # Check if database exists
    if not config.DATABASE_PATH.exists():
        console.print(
            f"\n❌ Database not found at: {config.DATABASE_PATH}",
            style="red",
        )
        console.print("\n💡 Run the following commands first:")
        console.print("   1. python -m superagent.data.fetch_nflverse")
        console.print("   2. python -m superagent.database")
        return False

    try:
        conn = duckdb.connect(str(config.DATABASE_PATH), read_only=True)
    except Exception as e:
        console.print(f"\n❌ Failed to connect to database: {e}", style="red")
        return False

    # Test 1: Check tables exist
    console.print("\n[bold]Test 1: Base Tables[/bold]")
    required_tables = ["plays", "games", "weekly", "rosters"]
    tables_result = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main';"
    ).fetchall()
    existing_tables = [t[0] for t in tables_result]

    for table in required_tables:
        if table in existing_tables:
            console.print(f"   ✅ {table}")
        else:
            console.print(f"   ❌ {table} (missing)", style="red")

    # Test 2: Row counts
    console.print("\n[bold]Test 2: Table Row Counts[/bold]")
    for table in required_tables:
        if table in existing_tables:
            try:
                result = conn.execute(f"SELECT COUNT(*) as cnt FROM {table}").fetchone()
                row_count = result[0] if result else 0
                console.print(f"   {table}: {row_count:,} rows")
            except Exception as e:
                console.print(f"   ❌ {table}: Error - {e}", style="red")

    # Test 3: Sample queries
    console.print("\n[bold]Test 3: Sample Queries[/bold]")

    queries = [
        (
            "Seasons in play_by_play data",
            "SELECT DISTINCT season FROM plays ORDER BY season DESC;",
        ),
        (
            "Teams in games data",
            "SELECT COUNT(DISTINCT home_team) as team_count FROM games;",
        ),
        (
            "Games by season",
            "SELECT season, COUNT(*) as game_count FROM games GROUP BY season ORDER BY season DESC LIMIT 10;",
        ),
        (
            "Sample plays",
            "SELECT game_id, play_id, posteam, play_type, yards_gained FROM plays LIMIT 5;",
        ),
    ]

    for query_name, query in queries:
        console.print(f"\n   📊 {query_name}")
        try:
            result = conn.execute(query).fetchall()
            if result:
                # Create table for display
                table = Table(show_header=True, header_style="bold cyan", show_lines=True)

                # Get column names
                desc = conn.execute(query).description
                for col in desc:
                    table.add_column(col[0])

                # Add rows
                for row in result:
                    table.add_row(*[str(v) if v is not None else "-" for v in row])

                console.print(table)
            else:
                console.print("   (No results)", style="dim")
        except Exception as e:
            console.print(f"      ❌ Query failed: {str(e)[:80]}", style="red")

    # Test 4: Check views
    console.print("\n[bold]Test 4: Derived Views[/bold]")
    views_result = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main' AND table_type = 'VIEW';"
    ).fetchall()
    existing_views = [v[0] for v in views_result]

    for view in ["team_week_epa", "player_season_stats", "qb_game_summary", "game_team_summary"]:
        if view in existing_views:
            console.print(f"   ✅ {view}")
        else:
            console.print(f"   ⚠️  {view} (not created)", style="yellow")

    # Summary
    console.print("\n" + "=" * 80)
    console.print("[green]✅ Validation complete![/green]")
    console.print("=" * 80)

    console.print("\n[bold]Next Steps:[/bold]")
    console.print("   1. Verify data looks correct in sample queries above")
    console.print("   2. Once verified, Phase 2 is ready: deterministic query tools")
    console.print("   3. See README.md for more information")

    conn.close()
    return True


def main():
    """CLI entry point."""
    success = validate_database()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
