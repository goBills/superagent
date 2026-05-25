# Production Deployment Checklist

Run through this before going live.

## Environment Variables

- [ ] `ANTHROPIC_API_KEY` is a valid API key.
- [ ] `ANTHROPIC_MODEL` is set or intentionally using the default.
- [ ] `SECRET_KEY` is a strong random string, not the development default.
- [ ] `ADMIN_TOKEN` is a strong random string before enabling `/admin`.
- [ ] `DATABASE_URL` points to PostgreSQL for shared production hosts.
- [ ] `ENVIRONMENT=production`.
- [ ] `TOKEN_EXPIRY_DAYS` is configured.
- [ ] `RATE_LIMIT_PER_HOUR` is configured.
- [ ] `BOOTSTRAP_NFL_DATA=true` for first deploy, unless `data/superagent.duckdb` is preloaded.
- [ ] `HOST=0.0.0.0`.
- [ ] `PORT` matches the hosting provider's expected port.

## Database

- [ ] PostgreSQL is provisioned for production.
- [ ] Automatic backups are enabled.
- [ ] Connection string is correct.
- [ ] Tables initialize on startup via `init_db()`.
- [ ] Persistent disk is mounted at `/app/data` if the host supports it.
- [ ] NFL DuckDB exists at `/app/data/superagent.duckdb` after first startup.

## Security

- [ ] HTTPS/TLS is enabled.
- [ ] API keys are only in environment variables.
- [ ] Database credentials are only in environment variables.
- [ ] `.env` is not committed.
- [ ] Rate limiting is active.
- [ ] CORS is appropriate for the deployed domain.

## Monitoring

- [ ] `/health` is accessible.
- [ ] Provider logs are accessible.
- [ ] Error monitoring or log alerts are configured if available.

## Functional Smoke Test

- [ ] `curl https://your-app/health` returns 200.
- [ ] `POST /auth/register` creates a user.
- [ ] `POST /auth/login` returns a token.
- [ ] `POST /chat` without token returns 401.
- [ ] `POST /chat` with token returns a structured response.
- [ ] `GET /sessions` works with token.

## Go Live

- [ ] All checks above pass.
- [ ] Public URL is stable.
- [ ] First 24 hours of logs are monitored.
- [ ] Feedback channel is ready.
