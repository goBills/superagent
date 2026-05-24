"""
Configuration management for Superagent.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()


class Config:
    """Configuration class for Superagent."""

    # Paths
    PROJECT_ROOT = Path(__file__).parent.parent.parent
    DATA_DIR = PROJECT_ROOT / "data"
    RAW_DATA_DIR = DATA_DIR / "raw"
    DATABASE_PATH = DATA_DIR / "superagent.duckdb"
    SCRIPTS_DIR = PROJECT_ROOT / "scripts"

    # API Configuration
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

    # Database Configuration
    DB_TIMEOUT = 30  # seconds

    # Data Configuration
    NFL_SEASONS = list(range(2020, 2026))  # 2020-2025
    BATCH_SIZE = 10000

    # Debug
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"

    @classmethod
    def ensure_directories(cls):
        """Ensure all required directories exist."""
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
        cls.RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
        cls.SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)


def get_config() -> Config:
    """Get the configuration object."""
    Config.ensure_directories()
    return Config
