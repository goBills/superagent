# Superagent: NFL Intelligence Platform

A sellable NFL research assistant that answers natural-language questions about stats, players, teams, trends, and game analysis. Powered by historical NFL data and Claude API.

## Status

**Phase 1: Data Layer Foundation** — Setting up nflverse data ingestion and DuckDB infrastructure.

## Quick Start

### Prerequisites
- Python 3.10+
- pip or uv

### Setup

1. **Navigate to the project:**
   ```bash
   cd "/Users/robertcapozzi/Documents/Football AI Project"
   ```

2. **Create a virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   pip install -e .
   ```

4. **Copy and configure environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env and add your ANTHROPIC_API_KEY (not needed until Phase 2)
   ```

## Phase 1: Data Foundation

### Step 1: Download nflverse Data

```bash
python -m superagent.data.fetch_nflverse
```

This downloads parquet files (2020-2025 seasons) to `data/raw/`.

**Note:** If network access is blocked, run this command when network is available.

### Step 2: Build DuckDB Database

```bash
python -m superagent.database
```

This loads season-specific parquet files into a local DuckDB database at `data/superagent.duckdb`.

### Step 3: Validate Data

```bash
python scripts/validate_data.py
```

This runs sanity checks and shows sample query results to confirm data loaded correctly.

## Project Structure

```
superagent/
├── src/superagent/
│   ├── __init__.py
│   ├── config.py                  # Configuration & environment
│   ├── database.py                # DuckDB setup & schema
│   ├── data/
│   │   ├── fetch_nflverse.py     # Download nflverse parquet files
│   ├── tools.py                   # Query tools (Phase 2, not implemented yet)
│   ├── agent.py                   # Claude agent (Phase 3, not implemented yet)
│   └── main.py                    # CLI entry point (Phase 3, not implemented yet)
├── data/
│   ├── raw/                       # Downloaded parquet files
│   └── superagent.duckdb         # DuckDB database
├── scripts/
│   └── validate_data.py           # Data validation
├── tests/                         # Pytest tests (Phase 2)
├── requirements.txt               # Python dependencies
├── pyproject.toml                 # Package metadata
├── .env.example                   # Environment template
├── .gitignore                     # Git ignore rules
└── README.md                      # This file
```

## Data Sources

- **Source:** nflverse/nflfastR historical data (parquet format)
- **Coverage:** 2020-2025 NFL seasons (regular + available postseason)
- **Format:** Parquet (native DuckDB support, no pandas conversion needed)

## Next Steps

After Phase 1 validation, we will implement:
- Phase 2: Deterministic query tools + pytest tests
- Phase 3: Claude agent + interactive CLI chat

## Known Limitations (MVP)

- Historical data through 2025 season only
- No live/current-week game updates
- No injury data or depth charts
- No betting recommendations
- No fantasy projections
- No predictions or ML models

## Development

### Install dev dependencies:
```bash
pip install -e ".[dev]"
```

### Run tests:
```bash
pytest
```

## License

MIT

## Contact

Built with ❤️ for NFL analytics.
