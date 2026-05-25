# Superagent: NFL Intelligence Platform

A sellable NFL research assistant that answers natural-language questions about stats, players, teams, trends, and game analysis. Powered by historical NFL data and Claude API.

## What Superagent Does

Superagent is a natural-language research assistant for NFL historical data from 2020-2025. Ask about stats, players, teams, EPA, fantasy metrics, draft research, schedules, bye weeks, and fantasy schedule context. It is historical research only: not betting advice, projections, live injury analysis, or start/sit picks.

### Quick Example

```
You: What's Josh Allen's EPA per play in 2024?
Agent: Josh Allen's EPA/play was 0.259 in 2024...

You: Compare him to Lamar Jackson
Agent: Josh Allen (0.259 EPA/play) vs Lamar Jackson (0.344 EPA/play)...

You: What should I know about Josh Allen's fantasy schedule for 2025?
Agent: Josh Allen plays for Buffalo, whose bye week is...
```

## Status

✅ **Phase 1: Data Layer** — nflverse data ingestion and DuckDB infrastructure complete.
✅ **Phase 2A: Deterministic Tools** — Name resolution + 4 core NFL query tools with pytest coverage.
✅ **Phase 3A: Claude Agent** — Tool-calling agent with error handling.
✅ **Phase 3B: Interactive CLI** — User-facing REPL for natural language questions.
✅ **Phase 3C: Conversation Memory** — CLI preserves recent turns for follow-up questions.
✅ **Phase 4A: Fantasy Research Tools** — Fantasy scoring summaries, comparisons, and weekly usage.
✅ **Phase 4B: Draft Research Tools** — Usage risers, target opportunity, and late-season breakouts.
✅ **Phase 5: Player EPA & Advanced Analytics** — Player EPA/play, success rate, CPOE, and position splits.
✅ **Phase 6: Web API & Demo UI** — FastAPI backend with browser-based chat interface and example prompts.
✅ **Phase 7A: Schedule + Bye Week Context** — Team schedules, bye weeks, and games from a specified week onward.
✅ **Phase 7C-lite: Fantasy Schedule Context** — Fantasy metrics + schedule context, no external data sources.
✅ **Phase 8: Product Layer** — User auth, persistent conversations, saved sessions, rate limits, and deployment-ready config.

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

You: What was Josh Allen's EPA per play in 2024?
Agent: Josh Allen's QB EPA/play was...
📊 Tools Used:
  ✅ get_player_advanced_summary

You: Compare Josh Allen and Lamar Jackson by EPA and CPOE in 2024
Agent: Here's their advanced comparison using EPA/play, success rate, and CPOE...
📊 Tools Used:
  ✅ compare_player_advanced

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

You: When are the Bills on bye in 2025?
Agent: The Bills are on bye in Week...
📊 Tools Used:
  ✅ get_bye_weeks

You: Show the Bills schedule for 2025
Agent: Here's Buffalo's 2025 schedule...
📊 Tools Used:
  ✅ get_team_schedule_context

You: Who do the Bills play from Week 10 on in 2025?
Agent: From Week 10 onward, Buffalo plays...
📊 Tools Used:
  ✅ get_upcoming_games

You: What should I know about Josh Allen's fantasy schedule in 2025?
Agent: Josh Allen plays for the Bills, whose bye week is...
📊 Tools Used:
  ✅ get_fantasy_schedule_context

You: Compare James Cook and Khalil Shakir fantasy context from Week 10 onward
Agent: James Cook (RB, BUF) and Khalil Shakir (WR, BUF) share the Bills schedule...
📊 Tools Used:
  ✅ compare_fantasy_context

You: help
Agent: [shows available question types]

You: exit
Goodbye! 👋
```

**Note on multi-turn:** The CLI preserves the last 6 turns of conversation, so follow-ups like "Compare him to Lamar" can use recent context.

## Phase 6: Web API & Demo UI

A lightweight browser interface to Superagent, perfect for demos and sharing.

### Start the Web Server

Once Phase 1 data is loaded and your API key is set:

```bash
python -m superagent.api
```

Then open **http://localhost:8000** in your browser.

### Features

- **Chat interface** — Ask questions in your browser
- **Authentication** — Register or sign in before using chat
- **Persistent sessions** — Browser stores session ID in `localStorage`, backend persists messages in SQLite/Postgres
- **Saved conversations** — API endpoints list, retrieve, export, and delete sessions
- **Rate limits** — Per-user hourly quota protects the API
- **Tools sidebar** — Collapsible list of tools used for each answer
- **Example buttons** — Quick-start queries:
  - "Josh Allen EPA/play"
  - "Bills RB usage"
  - "WR target opportunities"
  - "RB late-season breakouts"
  - "Bills bye week"
  - "Bills schedule"
  - "From Week 10"
  - "All bye weeks"
  - "Josh schedule"
  - "Compare context"
- **Disclaimer** — Clear footer stating "Historical research. Not betting/start-sit advice."

### Architecture

- **Backend:** FastAPI (wraps existing `run_agent()`)
- **Frontend:** Single HTML file with vanilla JS (no build, no node_modules)
- **Product database:** SQLite by default, PostgreSQL-ready via `DATABASE_URL`
- **Sessions:** Persistent per-user conversation history
- **CORS:** Localhost only (`http://localhost:8000`, `http://127.0.0.1:8000`)

### API Endpoints

**`GET /health`**
```bash
curl http://localhost:8000/health
```

**`POST /chat`**
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $SUPERAGENT_TOKEN" \
  -d '{
    "question": "What is Josh Allen EPa per play in 2024?",
    "session_id": "optional-uuid"
  }'
```

Response:
```json
{
  "ok": true,
  "answer": "Josh Allen's EPA/play in 2024 was 0.259, meaning...",
  "tools_used": [
    {
      "name": "get_player_advanced_summary",
      "input": {"player_name": "Josh Allen", "season": 2024},
      "result": {"ok": true, "data": {...}}
    }
  ],
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "error": null
}
```

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
   - `get_player_advanced_summary` — EPA/play, success rate, CPOE, and position-specific splits
   - `compare_player_advanced` — side-by-side advanced player metrics
   - `get_team_schedule_context` — full team schedule with bye week, results, and scores
   - `get_bye_weeks` — team-specific or league-wide bye weeks
   - `get_upcoming_games` — games from an explicit week onward
   - `get_fantasy_schedule_context` — player fantasy usage plus team bye and schedule context
   - `compare_fantasy_context` — compare multiple players' bye weeks, schedules, and usage trends
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
- Box-score, EPA, success rate, CPOE, fantasy research, historical draft research, schedule, bye-week, and fantasy schedule context (no projection/prediction)
- Historical data only (2020-2025)

## Project Structure

```
superagent/
├── src/superagent/
│   ├── __init__.py
│   ├── config.py                  # Configuration & environment
│   ├── auth.py                    # Password hashing + JWT helpers
│   ├── db.py                      # Product DB setup for auth/session persistence
│   ├── models.py                  # SQLAlchemy product-layer models
│   ├── rate_limit.py              # Per-user hourly rate limiting
│   ├── database.py                # DuckDB setup & schema
│   ├── db_query.py                # Safe query helpers + JSON serialization
│   ├── name_resolution.py         # Player/team fuzzy matching
│   ├── tools.py                   # deterministic NFL + fantasy query tools
│   ├── tool_schemas.py            # Claude tool definitions
│   ├── agent.py                   # Claude tool-calling agent
│   ├── cli.py                     # CLI formatting functions
│   ├── main.py                    # Interactive CLI entry point
│   ├── api.py                     # FastAPI web backend
│   ├── static/
│   │   └── index.html             # Web chat UI (single-page)
│   └── data/
│       ├── fetch_nflverse.py     # Download nflverse parquet files
│       └── build_database.py     # Load parquet → DuckDB
├── data/
│   ├── raw/                       # Downloaded parquet files (2020-2025)
│   └── superagent.duckdb         # DuckDB database
├── scripts/
│   ├── validate_data.py           # Data validation
│   ├── smoke_agent.py             # Manual agent test (requires API key)
│   └── demo_superagent.py         # Canned MVP demo flow (requires API key)
├── docs/
│   └── API.md                     # HTTP API reference
├── tests/
│   ├── test_tools.py              # 25 tests: name resolution + tools
│   ├── test_advanced.py           # 14 tests: player EPA + advanced analytics
│   ├── test_agent.py              # 15 tests: agent with mocked client
│   ├── test_auth.py               # 6 tests: register/login/rate limits
│   ├── test_cli.py                # 11 tests: CLI formatting
│   ├── test_draft_research.py     # 19 tests: draft research filters
│   ├── test_fantasy.py            # 22 tests: fantasy scoring + usage tools
│   ├── test_fantasy_schedule_context.py # 17 tests: fantasy schedule context
│   ├── test_api.py                # 9 tests: FastAPI endpoints + auth-aware chat
│   ├── test_persistence.py        # 4 tests: persistent sessions + export/delete
│   └── test_schedule_context.py   # 19 tests: schedule + bye week tools
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

All 161 tests passing:
- **Phase 2A (Tools):** 25 tests validating name resolution and 4 core tools
- **Phase 3A/3C (Agent):** 15 tests of Claude tool-calling and conversation history with mocked client (no API key needed)
- **Phase 3B (CLI):** 11 tests of formatting functions
- **Phase 4A (Fantasy):** 22 tests of fantasy scoring, player summaries, comparisons, and weekly usage
- **Phase 4B (Draft Research):** 19 tests of usage risers, target opportunity, late-season breakouts, and tool schemas
- **Phase 5 (Advanced):** 14 tests of player EPA, success rate, CPOE, small samples, comparisons, and tool schemas
- **Phase 6 (API):** 9 tests of FastAPI endpoints, session management, and CORS
- **Phase 7A (Schedule):** 19 tests of team schedules, bye weeks, games from week N onward, JSON safety, and tool schemas
- **Phase 7C-lite (Fantasy Context):** 17 tests of player fantasy schedule context, comparisons, missing-context notes, and tool schemas
- **Phase 8 (Product Layer):** 10 tests of auth, rate limits, persistent sessions, export, and delete

Run tests:
```bash
pytest                    # Run all tests
pytest tests/test_advanced.py  # Run advanced analytics tests only
pytest tests/test_cli.py  # Run CLI tests only
pytest tests/test_fantasy.py  # Run fantasy tests only
pytest tests/test_fantasy_schedule_context.py  # Run fantasy schedule context tests only
pytest tests/test_draft_research.py  # Run draft research tests only
pytest tests/test_schedule_context.py  # Run schedule context tests only
pytest -v                 # Verbose output
```

## MVP Demo Script

Run a canned walkthrough of the major MVP capabilities:

```bash
python scripts/demo_superagent.py
```

The script requires `ANTHROPIC_API_KEY` because it exercises the real Claude tool-calling path. It demonstrates EPA, player comparison, fantasy usage, draft research, bye weeks, schedule context, and fantasy schedule context.

## API Documentation

See [docs/API.md](docs/API.md) for request/response formats, error behavior, curl examples, and the full deterministic tool list.

## Known Limitations

**Current scope:**
- **No current-week awareness:** Schedule tools default to Week 1 unless you specify a week.
- **No live injury data:** Check NFL.com, ESPN, or fantasy platforms for current player status.
- **No depth charts:** Superagent uses historical rosters and stats, not current team depth charts.
- **No projections or predictions:** It summarizes historical data and research filters, not forecasts.
- **No betting recommendations:** Odds, lines, and market context are not available.
- **Simple product auth:** Email/password auth and JWTs are MVP-grade. OAuth, password reset, and admin controls are future work.

**By design:**
- No scraping or fragile external feeds in the MVP.
- No ML model for stat generation; Claude orchestrates deterministic tools.
- No gambling integration; informational research only.

These are intentional scope decisions, not bugs.

## Future Phases (Post-Phase 8)

- **Phase 7B: Injuries & Depth** — Legitimate injury/depth source, treated as an enrichment plugin once a source is chosen.
- **Phase 9: Deployment** — Production reverse proxy, hosted database, domain, monitoring, and stricter CORS.
- **Beyond** — Password reset, OAuth, admin controls, caching, commercial licensing, and domain-specific model tuning.

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
