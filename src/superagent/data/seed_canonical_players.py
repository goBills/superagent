"""
Seed canonical player identity from the local nflverse DuckDB.

Run with:
    python -m superagent.data.seed_canonical_players
"""

from __future__ import annotations

import argparse

from superagent.canonical_resolution import seed_canonical_players_from_nflverse


def main() -> None:
    """CLI entrypoint for seeding canonical player records."""
    parser = argparse.ArgumentParser(description="Seed canonical players from nflverse data")
    parser.add_argument(
        "--season",
        action="append",
        type=int,
        dest="seasons",
        help="Season to seed. Repeat for multiple seasons. Defaults to configured NFL_SEASONS.",
    )
    parser.add_argument(
        "--duckdb-path",
        help="Optional path to the nflverse DuckDB file.",
    )
    args = parser.parse_args()

    summary = seed_canonical_players_from_nflverse(
        seasons=args.seasons,
        duckdb_path=args.duckdb_path,
    )
    print("Canonical player seed complete:")
    for key, value in summary.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
