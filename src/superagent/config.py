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
    ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

    # Database Configuration
    DB_TIMEOUT = 30  # seconds
    PRODUCT_DATABASE_URL = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{DATA_DIR / 'superagent_product.db'}",
    )

    # Auth / Product Configuration
    SECRET_KEY = os.getenv(
        "SECRET_KEY",
        "dev-secret-key-change-in-production-min-32-chars",
    )
    ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
    TOKEN_EXPIRY_DAYS = int(os.getenv("TOKEN_EXPIRY_DAYS", "30"))
    RATE_LIMIT_PER_HOUR = int(os.getenv("RATE_LIMIT_PER_HOUR", "100"))
    HOST = os.getenv("HOST", "127.0.0.1")
    PORT = int(os.getenv("PORT", "8000"))
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "")  # Set by Render on deploy

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


# Module-level aliases for modules that prefer simple config imports.
ANTHROPIC_API_KEY = Config.ANTHROPIC_API_KEY
ANTHROPIC_MODEL = Config.ANTHROPIC_MODEL
DATABASE_URL = Config.PRODUCT_DATABASE_URL
SECRET_KEY = Config.SECRET_KEY
ADMIN_TOKEN = Config.ADMIN_TOKEN
TOKEN_EXPIRY_DAYS = Config.TOKEN_EXPIRY_DAYS
RATE_LIMIT_PER_HOUR = Config.RATE_LIMIT_PER_HOUR
HOST = Config.HOST
PORT = Config.PORT
ENVIRONMENT = Config.ENVIRONMENT
