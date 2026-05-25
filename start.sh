#!/bin/sh
set -e

echo "Starting Superagent..."

echo "Initializing product database..."
python -c "from superagent.db import init_db; init_db()"

echo "Checking API module..."
python -c "from superagent.api import app; print('API module loaded')"

echo "Ready. Starting API on http://${HOST:-0.0.0.0}:${PORT:-8000}"
exec python -m superagent.api
