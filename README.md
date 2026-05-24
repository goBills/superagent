# Superagent: NFL Intelligence Platform

A sellable NFL research assistant that answers natural-language questions about stats, players, teams, trends, and game analysis. Powered by historical NFL data and Claude API.

## Status

✅ **Phase 1: Data Layer** — nflverse data ingestion and DuckDB infrastructure complete.
✅ **Phase 2A: Deterministic Tools** — Name resolution + 4 core NFL query tools with pytest coverage.
✅ **Phase 3A: Claude Agent** — Tool-calling agent with error handling.
✅ **Phase 3B: Interactive CLI** — User-facing REPL for natural language questions.
✅ **Phase 3C: Conversation Memory** — CLI preserves recent turns for follow-up questions.
✅ **Phase 4A: Fantasy Research Tools** — Fantasy scoring summaries, comparisons, and weekly usage.
✅ **Phase 4B: Draft Research Tools** — Usage risers, target opportunity, and late-season breakouts.

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
   # Optional: set ANTHROPIC_MODEL=claude-sonnet-4-20250514
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

You: Compare James Cook and Khalil Shakir in PPR for 2024
Agent: Here's their fantasy comparison using PPR scoring...
📊 Tools Used:
  ✅ compare_fantasy_players

You: Show James Cook's weekly usage in 2024
Agent: Here's James Cook's weekly usage by carries, targets, receptions, yards, and PPR points...
📊 Tools Used:
  ✅ get_player_weekly_usage

You: Which WRs had 100+ targets in 2024?
Agent: Here are the high-target WRs with team target share...
📊 Tools Used:
  ✅ find_target_opportunity_players

You: Find late-season RB breakouts in 2024
Agent: Here are RBs whose opportunities and PPR scoring rose from weeks 1-8 to 9-17...
📊 Tools Used:
  ✅ find_late_season_breakouts

You: help
Agent: [shows available question types]

You: exit
Goodbye! 👋
```

**Note on multi-turn:** The CLI preserves the last 6 turns of conversation, so follow-ups like "Compare him to Lamar" can use recent context.

### How It Works

1. **You ask a question** in natural language
2. **Claude decides which tools to call:** 
   - `get_team_summary` — wins, losses, points, offensive/defensive EPA
   - `get_player_summary` — passing/rushing/receiving yards and TDs
   - `compare_players` — side-by-side stats for multiple players
   - `get_team_epa_trend` — weekly EPA breakdown over a range
   - `get_fantasy_player_summary` — fantasy points by standard, half-PPR, or PPR scoring
   - `compare_fantasy_players` — side-by-side fantasy comparison
   - `get_player_weekly_usage` — weekly carries, targets, receptions, yards, TDs, and PPR points
   - `find_usage_risers` — historical players whose opportunities and PPR/game increased
   - `find_target_opportunity_players` — players above a target threshold with team target share
   - `find_late_season_breakouts` — players who improved from weeks 1-8 to weeks 9-17
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
- Multi-turn Q&A with recent conversation memory capped at 6 turns
- Box-score, team EPA, fantasy research, and historical draft research metrics (no projection/prediction)
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
│   ├── tools.py                   # deterministic NFL + fantasy query tools
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
│   ├── test_agent.py              # 15 tests: agent with mocked client
│   ├── test_cli.py                # 11 tests: CLI formatting
│   ├── test_draft_research.py     # 19 tests: draft research filters
│   └── test_fantasy.py            # 22 tests: fantasy scoring + usage tools
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

All 92 tests passing:
- **Phase 2A (Tools):** 25 tests validating name resolution and 4 core tools
- **Phase 3A/3C (Agent):** 15 tests of Claude tool-calling and conversation history with mocked client (no API key needed)
- **Phase 3B (CLI):** 11 tests of formatting functions
- **Phase 4A (Fantasy):** 22 tests of fantasy scoring, player summaries, comparisons, and weekly usage
- **Phase 4B (Draft Research):** 19 tests of usage risers, target opportunity, late-season breakouts, and tool schemas

Run tests:
```bash
pytest                    # Run all tests
pytest tests/test_cli.py  # Run CLI tests only
pytest tests/test_fantasy.py  # Run fantasy tests only
pytest tests/test_draft_research.py  # Run draft research tests only
pytest -v                 # Verbose output
```

## Future Phases (Out of Scope)

Potential enhancements beyond MVP:
- **Phase 4C:** Historical waiver and trend finder
- **Phase 5:** Player EPA metrics and richer player analytics
- **Phase 6:** Web API (FastAPI) instead of CLI-only
- **Phase 7:** Live/current-week data integration
- **Phase 8:** Injury status, depth charts, Vegas lines (informational-only)
- **Phase 9:** Multi-user support with auth
- **Phase 10:** Caching layer for performance
- **Phase 11:** Fine-tuned model for domain-specific reasoning

## Known Limitations

**Phase 3C (Current):**
- ⚠️ **Short-term memory only:** CLI preserves recent turns in memory during the current session only. No persistence across sessions.
- ⚠️ **No player EPA/play:** `get_player_summary` returns box-score stats (yards, TDs, etc.), not EPA metrics. Team EPA available via `get_team_epa_trend`.

**MVP Scope:**
- Historical data through 2025 season only (no live/current-week updates)
- No injury data, depth charts, or Vegas lines
- No betting picks, fantasy projections, or predictions
- Fantasy and draft tools are research tools, not start/sit, waiver pickup, or draft-pick advice
- No ML models; Claude only orchestrates deterministic tools

**These are not bugs—they're intentional scope decisions. Persistent memory and player EPA metrics are future enhancements.**

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
