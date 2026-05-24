# Superagent: NFL Intelligence Platform

A sellable NFL research assistant that answers natural-language questions about stats, players, teams, trends, and game analysis. Powered by historical NFL data and Claude API.

## Status

✅ **Phase 1: Data Layer** — nflverse data ingestion and DuckDB infrastructure complete.
✅ **Phase 2A: Deterministic Tools** — Name resolution + 4 core NFL query tools with pytest coverage.
✅ **Phase 3A: Claude Agent** — Tool-calling agent with multi-turn reasoning and error handling.
✅ **Phase 3B: Interactive CLI** — User-facing REPL for natural language questions.

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

4. **Set up your environment:**
   ```bash
   cp .env.example .env
   # Edit .env and add your ANTHROPIC_API_KEY
   export ANTHROPIC_API_KEY=sk-...  # Your Anthropic API key
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

## Phase 3: Interactive CLI (Agent + Chat)

### Run the Superagent CLI

Once Phase 1 data is loaded, start the interactive CLI:

```bash
python -m superagent.main
```

Or if installed as a package:
```bash
superagent
```

### Example Questions

```
You: What's the Bills' record in 2024?
Agent: The Buffalo Bills went 13-4 in the 2024 season...
📊 Tools Used:
  ✅ get_team_summary

You: Get the Bills' EPA trend for weeks 1-5 of 2024
Agent: Here's the weekly EPA breakdown for the Bills weeks 1-5...
📊 Tools Used:
  ✅ get_team_epa_trend

You: Compare Josh Allen and Lamar Jackson in 2024
Agent: Josh Allen (QB, BUF) vs Lamar Jackson (QB, BAL)...
📊 Tools Used:
  ✅ compare_players

You: help
Agent: [shows available question types]

You: exit
Goodbye! 👋
```

**Note on multi-turn:** Each question is independent. The CLI loops but does not preserve conversation history, so pronouns like "him" or "them" won't resolve to previous questions. Ask self-contained questions.

### How It Works

1. **You ask a question** in natural language (single-turn)
2. **Claude decides which tools to call:** 
   - `get_team_summary` — wins, losses, points, offensive/defensive EPA
   - `get_player_summary` — passing/rushing/receiving yards and TDs
   - `compare_players` — side-by-side stats for multiple players
   - `get_team_epa_trend` — weekly EPA breakdown over a range
3. **Superagent executes tools** with deterministic SQL queries
4. **Claude synthesizes results** and provides a clear answer
5. **CLI formats and displays** the response with tables and stats

**Strengths:**
- Tool use for guaranteed accuracy (no AI hallucination of stats)
- All data backed by nflverse/nflfastR (validated source)
- Clear attribution of data sources
- 2025 player stats transparently marked as "derived from play-by-play"
- Graceful error handling (missing data, invalid names, etc.)

**Current scope:**
- Single-turn Q&A (no conversation memory)
- Box-score and EPA metrics (no projection/prediction)
- Historical data only (2020-2025)

## Project Structure

```
superagent/
├── src/superagent/
│   ├── __init__.py
│   ├── config.py                  # Configuration & environment
│   ├── database.py                # DuckDB setup & schema
│   ├── db_query.py                # Safe query helpers + JSON serialization
│   ├── name_resolution.py         # Player/team fuzzy matching
│   ├── tools.py                   # 4 core deterministic tools
│   ├── tool_schemas.py            # Claude tool definitions
│   ├── agent.py                   # Claude tool-calling agent
│   ├── cli.py                     # CLI formatting functions
│   ├── main.py                    # Interactive CLI entry point
│   └── data/
│       ├── fetch_nflverse.py     # Download nflverse parquet files
│       └── build_database.py     # Load parquet → DuckDB
├── data/
│   ├── raw/                       # Downloaded parquet files (2020-2025)
│   └── superagent.duckdb         # DuckDB database
├── scripts/
│   ├── validate_data.py           # Data validation
│   └── smoke_agent.py             # Manual agent test (requires API key)
├── tests/
│   ├── test_tools.py              # 25 tests: name resolution + tools
│   ├── test_agent.py              # 9 tests: agent with mocked client
│   └── test_cli.py                # 11 tests: CLI formatting
├── requirements.txt               # Python dependencies
├── pyproject.toml                 # Package metadata + console script
├── .env.example                   # Environment template
├── .gitignore                     # Git ignore rules
└── README.md                      # This file
```

## Data Sources

- **Source:** nflverse/nflfastR historical data (parquet format)
- **Coverage:** 2020-2025 NFL seasons (regular + available postseason)
- **Format:** Parquet (native DuckDB support, no pandas conversion needed)

## Test Coverage

All 45 tests passing:
- **Phase 2A (Tools):** 25 tests validating name resolution and 4 core tools
- **Phase 3A (Agent):** 9 tests of Claude tool-calling with mocked client (no API key needed)
- **Phase 3B (CLI):** 11 tests of formatting functions

Run tests:
```bash
pytest                    # Run all tests
pytest tests/test_cli.py  # Run CLI tests only
pytest -v                 # Verbose output
```

## Future Phases (Out of Scope)

Potential enhancements beyond MVP:
- **Phase 4:** Web API (FastAPI) instead of CLI-only
- **Phase 5:** Live/current-week data integration
- **Phase 6:** Injury status, depth charts, Vegas lines (informational-only)
- **Phase 7:** Multi-user support with auth
- **Phase 8:** Caching layer for performance
- **Phase 9:** Fine-tuned model for domain-specific reasoning

## Known Limitations

**Phase 3B (Current):**
- ⚠️ **Single-turn only:** CLI loops but doesn't preserve conversation history. Each question is independent.
- ⚠️ **No player EPA/play:** `get_player_summary` returns box-score stats (yards, TDs, etc.), not EPA metrics. Team EPA available via `get_team_epa_trend`.

**MVP Scope:**
- Historical data through 2025 season only (no live/current-week updates)
- No injury data, depth charts, or Vegas lines
- No betting picks, fantasy projections, or predictions
- No ML models; Claude only orchestrates deterministic tools

**These are not bugs—they're intentional scope decisions. Multi-turn memory and player EPA metrics are Phase 3C/4 enhancements.**

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
