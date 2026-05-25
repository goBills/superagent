"""
Download nflverse parquet files.

nflverse maintains historical NFL data in parquet format on GitHub releases.
This module downloads season-specific parquet files for 2020-2025 seasons.

GitHub: https://github.com/nflverse/nflverse-data
nflreadr docs: https://nflreadr.nflverse.com/
nflfastR load_pbp: https://www.nflfastr.com/reference/load_pbp.html

IMPORTANT: nflverse releases season-specific parquet files, not aggregate files.
Each season downloads separately (e.g., play_by_play_2024.parquet).
"""

import sys
from pathlib import Path
from typing import List, Tuple
import requests
from rich.console import Console
from rich.progress import Progress, DownloadColumn, BarColumn, TransferSpeedColumn, TimeRemainingColumn

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from superagent.config import get_config

console = Console()
config = get_config()

NFLVERSE_BASE_URL = "https://github.com/nflverse/nflverse-data/releases/download"

# Season-specific file configurations
# nflverse releases files per dataset per season
DOWNLOAD_CONFIGS = {
    "pbp": {
        "description": "Play-by-play data with EPA, WPA, and advanced metrics",
        "file_template": "play_by_play_{season}.parquet",
        "release_tag": "pbp",
        "seasons": config.NFL_SEASONS,
    },
    "schedules": {
        "description": "Game schedule, results, and team stats",
        "file_template": "games.parquet",
        "release_tag": "schedules",
        "seasons": [None],
    },
    "player_stats": {
        "description": "Weekly player stats",
        "file_template": "player_stats_{season}.parquet",
        "release_tag": "player_stats",
        "seasons": config.NFL_SEASONS,
        # nflverse has not published this file yet in the observed release feed.
        # Superagent derives 2025 player stats from play-by-play, so bootstrap
        # should continue when this optional file is absent.
        "optional_seasons": [2025],
    },
    "rosters": {
        "description": "Weekly rosters with positions and teams",
        "file_template": "roster_weekly_{season}.parquet",
        "release_tag": "weekly_rosters",
        "seasons": config.NFL_SEASONS,
    },
}


def verify_url_exists(url: str) -> bool:
    """Check if a URL is accessible."""
    try:
        response = requests.head(url, timeout=5, allow_redirects=True)
        return response.status_code == 200
    except requests.RequestException:
        return False


def download_file(url: str, destination: Path, file_description: str = "") -> bool:
    """Download a file from URL to destination with progress bar."""
    try:
        console.print(f"   📥 {file_description}")

        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()

        total_size = int(response.headers.get("content-length", 0))
        destination.parent.mkdir(parents=True, exist_ok=True)

        with Progress(
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=console,
            transient=True,
        ) as progress:
            task_id = progress.add_task("", total=total_size)

            with open(destination, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        progress.update(task_id, advance=len(chunk))

        console.print(f"      ✅ Saved: {destination.name}")
        return True

    except requests.RequestException as e:
        console.print(f"      ❌ Download failed: {e}", style="red")
        return False
    except IOError as e:
        console.print(f"      ❌ Failed to save file: {e}", style="red")
        return False


def fetch_nflverse_data() -> Tuple[bool, List[str]]:
    """
    Download all nflverse parquet files for 2020-2025 seasons.

    Returns season-specific files for play-by-play, schedules, player stats, and rosters.
    """
    console.print("\n" + "=" * 80)
    console.print("[bold cyan]Superagent: nflverse Data Downloader[/bold cyan]")
    console.print("=" * 80)

    console.print(f"\n📂 Destination: {config.RAW_DATA_DIR}")
    console.print(f"📊 Seasons: {config.NFL_SEASONS[0]}-{config.NFL_SEASONS[-1]}")
    console.print(f"📦 Datasets: play-by-play, schedules, player stats, rosters")

    # Verify URLs before downloading
    console.print("\n[bold]Step 1: Verifying URLs[/bold]")
    unavailable_files = []

    for dataset_name, config_info in DOWNLOAD_CONFIGS.items():
        console.print(f"\n📋 {dataset_name}:")
        for season in config_info["seasons"][:2]:  # Check first 2 season files, or the single aggregate file
            filename = config_info["file_template"].format(season=season)
            url = f"{NFLVERSE_BASE_URL}/{config_info['release_tag']}/{filename}"

            if verify_url_exists(url):
                console.print(f"   ✅ {filename}")
            else:
                console.print(f"   ⚠️  {filename} — URL not accessible", style="yellow")
                unavailable_files.append((dataset_name, season))

    if unavailable_files:
        console.print(
            "\n⚠️  Some URLs are inaccessible. This may indicate:",
            style="yellow",
        )
        console.print("   • nflverse file structure changed")
        console.print("   • Release tags are different")
        console.print("   • Files are not available for all seasons")
        console.print(
            "\nVerify at: https://github.com/nflverse/nflverse-data/releases"
        )
        console.print(
            "Update DOWNLOAD_CONFIGS in fetch_nflverse.py if release structure changed.\n"
        )
        return False, []

    # Download files
    console.print("\n[bold]Step 2: Downloading Season-Specific Files[/bold]")
    downloaded_files = []
    failed_files = []
    skipped_optional_files = []

    for dataset_name, config_info in DOWNLOAD_CONFIGS.items():
        console.print(f"\n📦 {dataset_name} ({config_info['description']}):")
        optional_seasons = set(config_info.get("optional_seasons", []))

        for season in config_info["seasons"]:
            filename = config_info["file_template"].format(season=season)
            destination = config.RAW_DATA_DIR / filename
            url = f"{NFLVERSE_BASE_URL}/{config_info['release_tag']}/{filename}"

            # Skip if exists
            if destination.exists():
                console.print(f"   ⏭️  {filename} (exists, skipping)")
                downloaded_files.append(str(destination))
                continue

            # Download
            success = download_file(url, destination, filename)
            if success:
                downloaded_files.append(str(destination))
            elif season in optional_seasons:
                console.print(
                    f"      ⚠️  Optional file unavailable; continuing without {filename}",
                    style="yellow",
                )
                skipped_optional_files.append(filename)
            else:
                failed_files.append(filename)

    # Summary
    console.print("\n" + "=" * 80)
    console.print("[bold]Download Summary[/bold]")
    console.print("=" * 80)
    console.print(f"✅ Downloaded: {len(downloaded_files)} file(s)")
    if skipped_optional_files:
        console.print(f"⚠️  Optional unavailable: {len(skipped_optional_files)} file(s)")
    console.print(f"❌ Failed: {len(failed_files)} file(s)")

    if skipped_optional_files:
        console.print("\n[yellow]Optional files skipped:[/yellow]")
        for name in skipped_optional_files:
            console.print(f"   • {name}")

    if failed_files:
        console.print("\n[yellow]Failed files:[/yellow]")
        for name in failed_files[:5]:  # Show first 5
            console.print(f"   • {name}")
        if len(failed_files) > 5:
            console.print(f"   ... and {len(failed_files) - 5} more")
        return False, downloaded_files

    console.print("\n[green]✅ All files downloaded successfully![/green]")
    console.print(f"📍 Location: {config.RAW_DATA_DIR}")
    return True, downloaded_files


def main():
    """CLI entry point."""
    success, files = fetch_nflverse_data()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
