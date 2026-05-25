#!/bin/sh
set -e

echo "Starting Superagent..."

NFL_DB_PATH="${NFL_DUCKDB_PATH:-data/superagent.duckdb}"

if [ ! -f "$NFL_DB_PATH" ]; then
    if [ "${BOOTSTRAP_NFL_DATA:-true}" = "true" ]; then
        echo "NFL DuckDB not found at ${NFL_DB_PATH}."
        echo "Downloading nflverse data and building DuckDB. This can take several minutes on first deploy..."
        python -m superagent.data.fetch_nflverse
        python -m superagent.database
    else
        echo "WARNING: NFL DuckDB not found at ${NFL_DB_PATH}; BOOTSTRAP_NFL_DATA=false, so football tools may fail."
    fi
fi

echo "Initializing product database..."
python -c "from superagent.db import init_db; init_db()"

echo "Checking API module..."
python -c "from superagent.api import app; print('API module loaded')"

echo "Ready. Starting API on http://${HOST:-0.0.0.0}:${PORT:-8000}"
exec python -m superagent.api
