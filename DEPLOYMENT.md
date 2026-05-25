# Superagent Deployment Guide

This guide packages Superagent for local Docker use and simple hosted deployment on Render, Railway, or Heroku.

## Quick Start: Docker Compose

```bash
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY, SECRET_KEY, and ADMIN_TOKEN.

docker compose up --build
```

Open [http://localhost:8000](http://localhost:8000).

## Docker Only

```bash
docker build -t superagent:latest .

docker run -p 8000:8000 \
  -e ANTHROPIC_API_KEY=sk-... \
  -e DATABASE_URL=sqlite:////app/data/superagent_product.db \
  -e SECRET_KEY=change-me-to-a-long-random-secret \
  -e ADMIN_TOKEN=change-me-to-a-random-admin-token \
  -e BOOTSTRAP_NFL_DATA=true \
  -e HOST=0.0.0.0 \
  -e PORT=8000 \
  -v "$(pwd)/data:/app/data" \
  superagent:latest
```

## Production Deployment

### Render

1. Push the repo to GitHub.
2. In Render, create a new Web Service from the repo.
3. Choose Docker deployment if using the included `Dockerfile`.
4. Add a persistent disk mounted at `/app/data` if your plan supports it. This keeps the NFL DuckDB across deploys/restarts.
5. Add a PostgreSQL database in Render.
5. Set environment variables:
   - `ANTHROPIC_API_KEY`
   - `ANTHROPIC_MODEL=claude-sonnet-4-20250514`
   - `DATABASE_URL` from Render PostgreSQL
   - `SECRET_KEY` as a strong random string
   - `ADMIN_TOKEN` as a strong random string for `/admin`
   - `BOOTSTRAP_NFL_DATA=true`
   - `ENVIRONMENT=production`
   - `TOKEN_EXPIRY_DAYS=30`
   - `RATE_LIMIT_PER_HOUR=100`
   - `HOST=0.0.0.0`
   - `PORT=8000`
6. Deploy and verify `/health`.

On first deploy, Superagent downloads nflverse parquet files and builds `data/superagent.duckdb` if it is missing. This can take several minutes. `player_stats_2025.parquet` is optional because Superagent derives 2025 player stats from play-by-play when weekly player stats are unavailable. Without a persistent disk, the app may need to rebuild this database after deploys or cold starts.

If using Render's native Python environment instead of Docker:

```bash
pip install -r requirements.txt
```

Start command:

```bash
PYTHONPATH=src python -m superagent.api
```

### Railway

1. Create a Railway project from GitHub.
2. Add the PostgreSQL plugin.
3. Set environment variables:
   - `ANTHROPIC_API_KEY`
   - `SECRET_KEY`
   - `ADMIN_TOKEN`
   - `ENVIRONMENT=production`
   - `HOST=0.0.0.0`
   - `PORT=8000`
4. Railway will provide `DATABASE_URL` for PostgreSQL.
5. Deploy and verify `/health`.

### Heroku

```bash
heroku login
heroku create superagent-yourusername
heroku addons:create heroku-postgresql:mini -a superagent-yourusername
heroku config:set ANTHROPIC_API_KEY=sk-... -a superagent-yourusername
heroku config:set SECRET_KEY=change-me-to-a-long-random-secret -a superagent-yourusername
heroku config:set ADMIN_TOKEN=change-me-to-a-random-admin-token -a superagent-yourusername
heroku config:set ENVIRONMENT=production -a superagent-yourusername
heroku config:set HOST=0.0.0.0 -a superagent-yourusername
git push heroku main
heroku logs --tail -a superagent-yourusername
```

If Heroku does not use the Dockerfile, set the start command to:

```bash
PYTHONPATH=src python -m superagent.api
```

## Production Checklist

- `ANTHROPIC_API_KEY` is set.
- `SECRET_KEY` is strong and not the development default.
- `ADMIN_TOKEN` is set to a strong random string before using `/admin`.
- `DATABASE_URL` points to PostgreSQL for shared production hosts.
- `BOOTSTRAP_NFL_DATA=true` for first deploy, unless you preloaded `data/superagent.duckdb`.
- Persistent disk mounted at `/app/data` if the host supports it.
- `ENVIRONMENT=production` is set.
- `TOKEN_EXPIRY_DAYS` is configured.
- `RATE_LIMIT_PER_HOUR` is configured.
- `HOST=0.0.0.0`.
- HTTPS/TLS is enabled by the provider.
- Provider logs are visible.
- Database backups are enabled.
- `/health` returns `{"ok": true}`.

## Health Check

```bash
bash scripts/healthcheck.sh http://localhost:8000
bash scripts/healthcheck.sh https://your-app.render.com
```

Expected:

```json
{"ok": true, "status": "healthy", "service": "Superagent API"}
```

## Troubleshooting

### API starts but chat returns an Anthropic key error

Set `ANTHROPIC_API_KEY` in the host environment and restart the service.

### Database connection refused

Check that `DATABASE_URL` is present and points to the provider's PostgreSQL connection string.

### Auth tokens stop working after redeploy

Tokens are signed by `SECRET_KEY`. Keep the same `SECRET_KEY` across deployments unless you intentionally want all users to sign in again.

### Container cannot import `superagent`

The Dockerfile sets `PYTHONPATH=/app/src`. If using a custom deployment command, include `PYTHONPATH=src`.

## Scaling

Superagent's API layer is stateless:

- Auth is JWT-based.
- Sessions and messages are persisted in the database.
- Rate limits are persisted per user/hour.

Multiple API instances can run behind a load balancer as long as they share the same database and `SECRET_KEY`.
