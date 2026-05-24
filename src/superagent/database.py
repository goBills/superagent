"""
DuckDB database setup and schema definition for Superagent.

Loads season-specific nflverse parquet files and creates base tables and views.
"""

import sys
from pathlib import Path
from typing import Optional
import duckdb
from rich.console import Console

sys.path.insert(0, str(Path(__file__).parent.parent))

from superagent.config import get_config

console = Console()
config = get_config()


class SuperagentDB:
    """DuckDB connection and schema manager for Superagent."""

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize database connection."""
        self.db_path = db_path or config.DATABASE_PATH
        self.conn: Optional[duckdb.DuckDBPyConnection] = None

    def connect(self) -> duckdb.DuckDBPyConnection:
        """Connect to DuckDB database."""
        try:
            self.conn = duckdb.connect(str(self.db_path))
            console.print(f"✅ Connected to: {self.db_path}")
            return self.conn
        except Exception as e:
            console.print(f"❌ Failed to connect: {e}", style="red")
            raise

    def load_parquet_tables(self) -> bool:
        """
        Load season-specific parquet files into base tables.

        Loads all season-specific parquet files from data/raw/ into unified tables.
        For example:
        - play_by_play_2020.parquet, play_by_play_2021.parquet, etc. → plays table
        - schedules_2020.parquet, schedules_2021.parquet, etc. → games table
        """
        if not self.conn:
            self.connect()

        console.print("\n[bold]Loading parquet files into DuckDB...[/bold]")

        # Map dataset to table name and file pattern
        datasets = {
            "plays": {
                "file_pattern": "play_by_play_*.parquet",
                "description": "Play-by-play data (all seasons)",
            },
            "games": {
                "file_pattern": "games.parquet",
                "description": "Game schedules and results",
            },
            "weekly": {
                "file_pattern": "player_stats_*.parquet",
                "description": "Weekly player stats",
            },
            "rosters": {
                "file_pattern": "roster_weekly_*.parquet",
                "description": "Weekly rosters",
            },
        }

        loaded_tables = []
        failed_tables = []

        for table_name, dataset_info in datasets.items():
            try:
                # Find matching files
                file_pattern = dataset_info["file_pattern"]
                matching_files = list(config.RAW_DATA_DIR.glob(file_pattern))

                if not matching_files:
                    console.print(
                        f"⚠️  {table_name}: No files matching {file_pattern}",
                        style="yellow",
                    )
                    failed_tables.append(table_name)
                    continue

                # Sort files by season for consistent loading
                matching_files = sorted(matching_files)

                console.print(f"\n✅ {table_name}:")
                console.print(f"   Description: {dataset_info['description']}")
                console.print(f"   Files: {len(matching_files)} parquet file(s)")

                # Drop existing table
                self.conn.execute(f"DROP TABLE IF EXISTS {table_name};")

                # Load and combine all matching files
                # DuckDB can glob multiple files in read_parquet
                file_glob = str(config.RAW_DATA_DIR / file_pattern)
                self.conn.execute(
                    f"CREATE TABLE {table_name} AS SELECT * FROM read_parquet('{file_glob}');"
                )

                # Get row count and column count
                row_result = self.conn.execute(
                    f"SELECT COUNT(*) as cnt FROM {table_name};"
                ).fetchone()
                row_count = row_result[0] if row_result else 0

                col_result = self.conn.execute(
                    f"SELECT COUNT(*) as cnt FROM information_schema.columns WHERE table_name='{table_name}';"
                ).fetchone()
                col_count = col_result[0] if col_result else 0

                console.print(f"   ✅ Loaded: {row_count:,} rows × {col_count} columns")
                loaded_tables.append(table_name)

            except Exception as e:
                console.print(f"❌ {table_name}: {str(e)[:80]}", style="red")
                failed_tables.append(table_name)

        # Summary
        if failed_tables:
            console.print(f"\n⚠️  {len(failed_tables)} table(s) failed to load")
            return False

        console.print(f"\n✅ All {len(loaded_tables)} tables loaded successfully!")
        return True

    def create_derived_views(self) -> bool:
        """Create derived views for common queries."""
        if not self.conn:
            self.connect()

        console.print("\n[bold]Creating derived views...[/bold]")

        views = {
            "team_week_epa": """
                CREATE OR REPLACE VIEW team_week_epa AS
                SELECT
                    season,
                    week,
                    home_team AS team,
                    away_team AS opponent,
                    1 AS is_home,
                    SUM(CASE WHEN posteam = home_team THEN epa ELSE 0 END) AS offensive_epa,
                    SUM(CASE WHEN posteam = away_team THEN epa ELSE 0 END) AS defensive_epa_allowed,
                    SUM(CASE WHEN posteam = home_team THEN epa ELSE 0 END)
                        - SUM(CASE WHEN posteam = away_team THEN epa ELSE 0 END) AS net_epa,
                    COUNT(*) AS play_count
                FROM plays
                GROUP BY season, week, home_team, away_team
                UNION ALL
                SELECT
                    season,
                    week,
                    away_team AS team,
                    home_team AS opponent,
                    0 AS is_home,
                    SUM(CASE WHEN posteam = away_team THEN epa ELSE 0 END) AS offensive_epa,
                    SUM(CASE WHEN posteam = home_team THEN epa ELSE 0 END) AS defensive_epa_allowed,
                    SUM(CASE WHEN posteam = away_team THEN epa ELSE 0 END)
                        - SUM(CASE WHEN posteam = home_team THEN epa ELSE 0 END) AS net_epa,
                    COUNT(*) AS play_count
                FROM plays
                GROUP BY season, week, away_team, home_team
            """,
            "game_team_summary": """
                CREATE OR REPLACE VIEW game_team_summary AS
                SELECT
                    game_id,
                    season,
                    week,
                    home_team AS team,
                    away_team AS opponent,
                    1 AS is_home,
                    SUM(CASE WHEN posteam = home_team AND play_type IN ('pass', 'run')
                        THEN COALESCE(passing_yards, 0) + COALESCE(rushing_yards, 0) ELSE 0 END) AS offensive_yards,
                    SUM(CASE WHEN posteam = home_team THEN epa ELSE 0 END) AS offensive_epa,
                    SUM(CASE WHEN posteam = away_team THEN epa ELSE 0 END) AS defensive_epa_allowed,
                    COUNT(*) AS play_count
                FROM plays
                GROUP BY game_id, season, week, home_team, away_team
                UNION ALL
                SELECT
                    game_id,
                    season,
                    week,
                    away_team AS team,
                    home_team AS opponent,
                    0 AS is_home,
                    SUM(CASE WHEN posteam = away_team AND play_type IN ('pass', 'run')
                        THEN COALESCE(passing_yards, 0) + COALESCE(rushing_yards, 0) ELSE 0 END) AS offensive_yards,
                    SUM(CASE WHEN posteam = away_team THEN epa ELSE 0 END) AS offensive_epa,
                    SUM(CASE WHEN posteam = home_team THEN epa ELSE 0 END) AS defensive_epa_allowed,
                    COUNT(*) AS play_count
                FROM plays
                GROUP BY game_id, season, week, home_team, away_team
            """,
            "player_season_stats": """
                CREATE OR REPLACE VIEW player_season_stats AS
                WITH weekly_seasons AS (
                    SELECT DISTINCT season FROM weekly
                ),
                weekly_player_stats AS (
                    SELECT
                        season,
                        player_id,
                        player_name,
                        recent_team AS team,
                        COUNT(DISTINCT week) AS games,
                        SUM(COALESCE(attempts, 0)) AS passing_attempts,
                        SUM(COALESCE(completions, 0)) AS completions,
                        SUM(COALESCE(passing_yards, 0)) AS passing_yards,
                        SUM(COALESCE(passing_tds, 0)) AS passing_tds,
                        SUM(COALESCE(interceptions, 0)) AS interceptions,
                        SUM(COALESCE(carries, 0)) AS carries,
                        SUM(COALESCE(rushing_yards, 0)) AS rushing_yards,
                        SUM(COALESCE(rushing_tds, 0)) AS rushing_tds,
                        SUM(COALESCE(targets, 0)) AS targets,
                        SUM(COALESCE(receptions, 0)) AS receptions,
                        SUM(COALESCE(receiving_yards, 0)) AS receiving_yards,
                        SUM(COALESCE(receiving_tds, 0)) AS receiving_tds,
                        'weekly' AS source
                    FROM weekly
                    GROUP BY season, player_id, player_name, recent_team
                ),
                pbp_player_events AS (
                    SELECT
                        season,
                        passer_player_id AS player_id,
                        passer_player_name AS player_name,
                        posteam AS team,
                        week,
                        SUM(COALESCE(pass_attempt, 0)) AS passing_attempts,
                        SUM(COALESCE(complete_pass, 0)) AS completions,
                        SUM(COALESCE(passing_yards, 0)) AS passing_yards,
                        SUM(COALESCE(pass_touchdown, 0)) AS passing_tds,
                        SUM(COALESCE(interception, 0)) AS interceptions,
                        0 AS carries,
                        0 AS rushing_yards,
                        0 AS rushing_tds,
                        0 AS targets,
                        0 AS receptions,
                        0 AS receiving_yards,
                        0 AS receiving_tds
                    FROM plays
                    WHERE passer_player_id IS NOT NULL
                        AND season NOT IN (SELECT season FROM weekly_seasons)
                    GROUP BY season, passer_player_id, passer_player_name, posteam, week
                    UNION ALL
                    SELECT
                        season,
                        rusher_player_id AS player_id,
                        rusher_player_name AS player_name,
                        posteam AS team,
                        week,
                        0 AS passing_attempts,
                        0 AS completions,
                        0 AS passing_yards,
                        0 AS passing_tds,
                        0 AS interceptions,
                        SUM(COALESCE(rush_attempt, 0)) AS carries,
                        SUM(COALESCE(rushing_yards, 0)) AS rushing_yards,
                        SUM(COALESCE(rush_touchdown, 0)) AS rushing_tds,
                        0 AS targets,
                        0 AS receptions,
                        0 AS receiving_yards,
                        0 AS receiving_tds
                    FROM plays
                    WHERE rusher_player_id IS NOT NULL
                        AND season NOT IN (SELECT season FROM weekly_seasons)
                    GROUP BY season, rusher_player_id, rusher_player_name, posteam, week
                    UNION ALL
                    SELECT
                        season,
                        receiver_player_id AS player_id,
                        receiver_player_name AS player_name,
                        posteam AS team,
                        week,
                        0 AS passing_attempts,
                        0 AS completions,
                        0 AS passing_yards,
                        0 AS passing_tds,
                        0 AS interceptions,
                        0 AS carries,
                        0 AS rushing_yards,
                        0 AS rushing_tds,
                        COUNT(*) AS targets,
                        SUM(COALESCE(complete_pass, 0)) AS receptions,
                        SUM(COALESCE(receiving_yards, 0)) AS receiving_yards,
                        SUM(COALESCE(pass_touchdown, 0)) AS receiving_tds
                    FROM plays
                    WHERE receiver_player_id IS NOT NULL
                        AND season NOT IN (SELECT season FROM weekly_seasons)
                    GROUP BY season, receiver_player_id, receiver_player_name, posteam, week
                ),
                pbp_player_stats AS (
                    SELECT
                        season,
                        player_id,
                        player_name,
                        team,
                        COUNT(DISTINCT week) AS games,
                        SUM(passing_attempts) AS passing_attempts,
                        SUM(completions) AS completions,
                        SUM(passing_yards) AS passing_yards,
                        SUM(passing_tds) AS passing_tds,
                        SUM(interceptions) AS interceptions,
                        SUM(carries) AS carries,
                        SUM(rushing_yards) AS rushing_yards,
                        SUM(rushing_tds) AS rushing_tds,
                        SUM(targets) AS targets,
                        SUM(receptions) AS receptions,
                        SUM(receiving_yards) AS receiving_yards,
                        SUM(receiving_tds) AS receiving_tds,
                        'pbp_derived' AS source
                    FROM pbp_player_events
                    GROUP BY season, player_id, player_name, team
                )
                SELECT
                    season,
                    player_id,
                    player_name,
                    team,
                    games,
                    passing_attempts,
                    completions,
                    passing_yards,
                    passing_tds,
                    interceptions,
                    carries,
                    rushing_yards,
                    rushing_tds,
                    targets,
                    receptions,
                    receiving_yards,
                    receiving_tds,
                    source
                FROM weekly_player_stats
                UNION ALL
                SELECT
                    season,
                    player_id,
                    player_name,
                    team,
                    games,
                    passing_attempts,
                    completions,
                    passing_yards,
                    passing_tds,
                    interceptions,
                    carries,
                    rushing_yards,
                    rushing_tds,
                    targets,
                    receptions,
                    receiving_yards,
                    receiving_tds,
                    source
                FROM pbp_player_stats
            """,
            "qb_game_summary": """
                CREATE OR REPLACE VIEW qb_game_summary AS
                SELECT
                    season,
                    week,
                    player_id,
                    player_name,
                    recent_team AS team,
                    completions,
                    attempts,
                    passing_yards,
                    passing_tds,
                    interceptions,
                    carries,
                    rushing_yards,
                    rushing_tds
                FROM weekly
                WHERE COALESCE(attempts, 0) > 0
            """,
        }

        created = 0
        for view_name, view_sql in views.items():
            try:
                self.conn.execute(view_sql)
                console.print(f"✅ {view_name}")
                created += 1
            except Exception as e:
                console.print(
                    f"⚠️  {view_name}: {str(e)[:60]}",
                    style="yellow",
                )

        if created > 0:
            console.print(f"\n✅ {created} view(s) created")
        return True

    def init_database(self) -> bool:
        """Full database initialization."""
        console.print("\n" + "=" * 80)
        console.print("[bold cyan]Superagent: Database Initialization[/bold cyan]")
        console.print("=" * 80)

        try:
            self.connect()
        except Exception:
            return False

        if not self.load_parquet_tables():
            console.print("\n⚠️  Failed to load parquet tables", style="red")
            return False

        if not self.create_derived_views():
            console.print("\n⚠️  Some views failed (non-critical)", style="yellow")

        console.print("\n" + "=" * 80)
        console.print("[green]✅ Database initialization complete![/green]")
        console.print("=" * 80)
        return True

    def get_connection(self) -> duckdb.DuckDBPyConnection:
        """Get or create connection."""
        if not self.conn:
            self.connect()
        return self.conn

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()


if __name__ == "__main__":
    db = SuperagentDB()
    success = db.init_database()
    db.close()
    sys.exit(0 if success else 1)
