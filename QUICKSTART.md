# Superagent Phase 1 — Quick Start Guide

## 🚀 Get Started in 4 Steps

### 1️⃣ Set Up Python Environment
```bash
cd "/Users/robertcapozzi/Documents/Football AI Project"
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

### 2️⃣ Download nflverse Data
```bash
python3 -m superagent.data.fetch_nflverse
```
Downloads season-specific parquet files (2020-2025) to `data/raw/`

### 3️⃣ Initialize DuckDB Database
```bash
python3 -m superagent.database
```
Loads season-specific parquet files into `data/superagent.duckdb`

### 4️⃣ Validate Data
```bash
python3 scripts/validate_data.py
```
Runs sanity checks and shows sample queries

---

## 📋 What Gets Created

| Step | Outputs |
|------|---------|
| Step 2 | `data/raw/*.parquet` (plays, games, weekly, rosters) |
| Step 3 | `data/superagent.duckdb` (DuckDB database with 4 tables + 4 views) |
| Step 4 | Console output with validation results and sample data |

---

## ✅ Success Looks Like

After Step 4, you should see:
- ✅ All 4 base tables loaded with millions of rows
- ✅ 4 derived views created
- ✅ Sample queries returning data (seasons, teams, games, plays)
- ✅ No critical errors

---

## 🔍 Key Files

- **`src/superagent/data/fetch_nflverse.py`** — Downloads nflverse parquet files
- **`src/superagent/database.py`** — Loads parquet → DuckDB, creates schema
- **`scripts/validate_data.py`** — Tests database and shows sample results
- **`README.md`** — Full documentation
- **`PHASE_1_COMPLETE.md`** — Detailed Phase 1 notes

---

## ⚠️ Troubleshooting

**"ModuleNotFoundError"**
```bash
pip install -r requirements.txt
pip install -e .
```

**"Database not found"**
Make sure you ran Step 3 first.

**"URL not accessible" during download**
Check https://github.com/nflverse/nflverse-data/releases and update URLs in `fetch_nflverse.py` if they changed.

---

## 📊 Data Overview

Once Phase 1 completes, you'll have:
- **Play-by-play**: ~2.5M plays (1999-2025, but Phase 1 focuses on 2020-2025)
- **Games**: 7,000+ games (2020-2025)
- **Weekly stats**: Player weekly performance
- **Rosters**: Players, positions, teams

All queryable via DuckDB, ready for Phase 2 (deterministic tools).

---

## 🎯 Next

After Phase 1 validation succeeds:
- **Phase 2**: Build query tools (`get_team_summary()`, `get_player_summary()`, etc.)
- **Phase 3**: Wire Claude agent
- **Phase 4**: Build CLI chat interface

---

**Status**: Phase 1 code-complete. Ready for setup and validation.
