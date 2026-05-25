# Superagent API Reference

Superagent exposes a FastAPI service for authenticated web/API use. It wraps the same Claude tool-calling agent used by the CLI, while adding persistent sessions, saved conversations, and per-user rate limits.

## Endpoint: GET /health

Liveness check.

```bash
curl http://localhost:8000/health
```

Example response:

```json
{
  "ok": true,
  "status": "healthy",
  "service": "Superagent API"
}
```

## Endpoint: POST /auth/register

Create a user and return a JWT.

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "rob@example.com", "password": "password123"}'
```

Response:

```json
{
  "ok": true,
  "token": "jwt-token",
  "user_id": 1,
  "email": "rob@example.com",
  "error": null
}
```

## Endpoint: POST /auth/login

Log in an existing user and return a JWT.

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "rob@example.com", "password": "password123"}'
```

Use the token as:

```bash
Authorization: Bearer jwt-token
```

## Endpoint: POST /chat

Ask a natural-language question and get a research answer with tool transparency.

### Request

Requires `Authorization: Bearer <token>`.

```json
{
  "question": "What's Josh Allen's EPA per play in 2024?",
  "session_id": "optional-uuid-for-multi-turn"
}
```

Fields:
- `question` (required, string): Natural-language NFL research question.
- `session_id` (optional, string): Saved conversation ID for multi-turn context.

### Response

```json
{
  "ok": true,
  "answer": "Josh Allen's EPA/play in 2024 was 0.259...",
  "tools_used": [
    {
      "name": "get_player_advanced_summary",
      "input": {
        "player_name": "Josh Allen",
        "season": 2024
      },
      "result": {
        "ok": true,
        "data": {
          "epa_per_play": 0.259
        }
      }
    }
  ],
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "error": null
}
```

Fields:
- `ok` (boolean): Success indicator.
- `answer` (string or null): Claude's synthesis of deterministic tool results.
- `tools_used` (array): Tool calls with name, input parameters, and structured result.
- `session_id` (string): Saved conversation ID. Reuse it for follow-up questions.
- `error` (string or null): Error message when `ok` is false.

### Error Responses

Empty question:

```json
{
  "detail": "Question cannot be empty"
}
```

Missing/invalid token:

```json
{
  "detail": "Missing authorization token"
}
```

Rate limit exceeded:

```json
{
  "detail": "Rate limit exceeded. Try again later."
}
```

Missing Anthropic key returns an error payload so the web UI can display setup guidance:

```json
{
  "ok": false,
  "answer": null,
  "tools_used": [],
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "error": "ANTHROPIC_API_KEY not configured. Set it in .env or environment."
}
```

### Examples

Simple question:

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $SUPERAGENT_TOKEN" \
  -d '{"question": "What is Josh Allen'\''s EPA per play in 2024?"}'
```

Multi-turn conversation:

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $SUPERAGENT_TOKEN" \
  -d '{"question": "Tell me about Josh Allen in 2024"}'
```

Use the `session_id` from the first response:

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $SUPERAGENT_TOKEN" \
  -d '{
    "question": "How did he compare to Lamar Jackson?",
    "session_id": "550e8400-e29b-41d4-a716-446655440000"
  }'
```

## Saved Sessions

All endpoints require `Authorization: Bearer <token>`.

### GET /sessions

List saved sessions for the current user.

```bash
curl http://localhost:8000/sessions \
  -H "Authorization: Bearer $SUPERAGENT_TOKEN"
```

### GET /sessions/{session_id}

Return messages for one saved conversation.

```bash
curl http://localhost:8000/sessions/550e8400-e29b-41d4-a716-446655440000 \
  -H "Authorization: Bearer $SUPERAGENT_TOKEN"
```

### GET /sessions/{session_id}/export

Export one saved conversation as JSON.

```bash
curl http://localhost:8000/sessions/550e8400-e29b-41d4-a716-446655440000/export \
  -H "Authorization: Bearer $SUPERAGENT_TOKEN"
```

### DELETE /sessions/{session_id}

Delete one saved conversation.

```bash
curl -X DELETE http://localhost:8000/sessions/550e8400-e29b-41d4-a716-446655440000 \
  -H "Authorization: Bearer $SUPERAGENT_TOKEN"
```

## League Settings

League endpoints require the same bearer token as `/chat`. Users can own multiple leagues.

### POST /leagues

Create a league:

```bash
curl -X POST http://localhost:8000/leagues \
  -H "Authorization: Bearer $SUPERAGENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "league_name": "Home League",
    "league_type": "snake",
    "settings": {
      "ppr_type": "ppr",
      "num_teams": 12,
      "superflex_slots": 1,
      "passing_td_points": 6
    }
  }'
```

### GET /leagues

List the current user's leagues:

```bash
curl http://localhost:8000/leagues \
  -H "Authorization: Bearer $SUPERAGENT_TOKEN"
```

### GET /leagues/{league_id}

Retrieve one league:

```bash
curl http://localhost:8000/leagues/1 \
  -H "Authorization: Bearer $SUPERAGENT_TOKEN"
```

### PUT /leagues/{league_id}

Update league settings:

```bash
curl -X PUT http://localhost:8000/leagues/1 \
  -H "Authorization: Bearer $SUPERAGENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "league_name": "Home League",
    "league_type": "auction",
    "settings": {
      "ppr_type": "half_ppr",
      "num_teams": 12,
      "superflex_slots": 0,
      "passing_td_points": 4
    }
  }'
```

## ESPN Integration

### POST /integrations/espn/leagues

Fetch an ESPN fantasy football league and store its settings, rosters, and draft picks.

```bash
curl -X POST http://localhost:8000/integrations/espn/leagues \
  -H "Authorization: Bearer $SUPERAGENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "espn_league_id": 123456,
    "season": 2025,
    "espn_s2": "optional-private-league-cookie",
    "swid": "optional-private-league-cookie"
  }'
```

Public leagues may not need `espn_s2`/`swid`. Private leagues do.

## Admin Question Review

Admin endpoints are protected by the `ADMIN_TOKEN` environment variable. They are intended for the operator to review product feedback and should not be shared publicly.

### GET /admin

Serve the browser admin page:

```text
http://localhost:8000/admin?token=your-admin-token
```

### GET /admin/questions

Return recent user questions from the existing persisted `messages` table.

```bash
curl "http://localhost:8000/admin/questions?token=$ADMIN_TOKEN&limit=100"
```

Example response:

```json
[
  {
    "id": 42,
    "user_email": "rob@example.com",
    "user_id": 1,
    "timestamp": "2026-05-25T18:30:00",
    "question": "What was Josh Allen's EPA per play in 2024?",
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "tools_used": ["get_player_advanced_summary"],
    "response_preview": "Josh Allen's EPA/play was 0.259..."
  }
]
```

### GET /admin/questions/summary

Return aggregate counts:

```bash
curl "http://localhost:8000/admin/questions/summary?token=$ADMIN_TOKEN"
```

Example response:

```json
{
  "total_questions": 128,
  "unique_sessions": 47,
  "unique_users": 12,
  "timestamp": "2026-05-25T18:35:00"
}
```

### POST /admin/seed-canonical

Seed canonical players from nflverse into the product database. This is the production-safe replacement for running `python -m superagent.data.seed_canonical_players` when shell access is unavailable.

By default this endpoint runs a quick roster-only seed, which is enough for DraftSheets imports. Add `full_aliases=true` later to run slower weekly/play-by-play alias enrichment.

```bash
curl -X POST "https://superagent-ph31.onrender.com/admin/seed-canonical?token=$ADMIN_TOKEN&season=2025"
```

Example response:

```json
{
  "ok": true,
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued",
  "status_url": "/admin/jobs/550e8400-e29b-41d4-a716-446655440000?token=YOUR_ADMIN_TOKEN"
}
```

Poll job status:

```bash
curl "https://superagent-ph31.onrender.com/admin/jobs/550e8400-e29b-41d4-a716-446655440000?token=$ADMIN_TOKEN"
```

Completed response:

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "type": "seed_canonical",
  "status": "completed",
  "result": {
    "players_created": 128,
    "players_seen": 2834,
    "player_seasons_created": 2812,
    "aliases_created": 391
  },
  "error": null
}
```

### POST /admin/draft-import

Upload and import a DraftSheets CSV/XLSX file through the same strict importer used by the CLI. This is useful on Render Free, where shell access is unavailable.

```bash
curl -X POST "https://superagent-ph31.onrender.com/admin/draft-import?token=$ADMIN_TOKEN&source=draftsheetsv6&season=2025&sheet=DATA" \
  -F "file=@/path/to/Copy of DraftSheets Fantasy Tool.xlsx"
```

Malformed files return `400` with the strict validation error. Unknown or ambiguous players are imported into the existing review queue instead of being silently guessed.

Example response:

```json
{
  "ok": true,
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued",
  "status_url": "/admin/jobs/550e8400-e29b-41d4-a716-446655440000?token=YOUR_ADMIN_TOKEN"
}
```

Poll `/admin/jobs/{job_id}` for the final import summary.
While the job is running, the response includes a `progress` object with the current stage, row counts, and `updated_at` timestamp.

### GET /admin/draft-mappings

Return low-confidence draft source mappings queued for review:

```bash
curl "http://localhost:8000/admin/draft-mappings?token=$ADMIN_TOKEN&status=pending"
```

Example response:

```json
[
  {
    "id": 7,
    "source": "draftsheetsv6",
    "season": 2025,
    "source_player_name": "Future Rookie",
    "source_player_id": null,
    "status": "pending",
    "created_at": "2026-05-25T19:10:00",
    "resolved_at": null,
    "candidates": []
  }
]
```

### POST /admin/create-default-league

Create a league for an existing user without needing to retrieve a JWT manually.

```bash
curl -X POST "https://superagent-ph31.onrender.com/admin/create-default-league?token=$ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "user_email": "rgcapozzi@gmail.com",
    "league_name": "Your League Name",
    "league_type": "snake",
    "num_teams": 14,
    "roster_spots": 16,
    "ppr_type": "half_ppr",
    "passing_td_points": 4,
    "rushing_td_points": 6,
    "receiving_td_points": 6,
    "passing_yards_per_point": 25,
    "rushing_yards_per_point": 10,
    "receiving_yards_per_point": 10
  }'
```

Example response:

```json
{
  "ok": true,
  "league_id": 1,
  "user_id": 1,
  "settings_applied": true
}
```

## Tools Available

The agent can call these deterministic tools:

- `get_team_summary` — Team season stats, record, scoring, EPA.
- `get_player_summary` — Player box-score season totals.
- `compare_players` — Side-by-side player comparison.
- `get_team_epa_trend` — Weekly team EPA over a range.
- `get_fantasy_player_summary` — Fantasy points by scoring format.
- `compare_fantasy_players` — Fantasy comparison.
- `get_player_weekly_usage` — Weekly carries, targets, receptions, yards, TDs, and PPR points.
- `find_usage_risers` — Historical players whose opportunities increased.
- `find_target_opportunity_players` — High-target players with team target share.
- `find_late_season_breakouts` — Players who improved from weeks 1-8 to 9-17.
- `get_player_advanced_summary` — EPA/play, success rate, CPOE, and position splits.
- `compare_player_advanced` — Advanced analytics comparison.
- `get_team_schedule_context` — Full schedule with bye week.
- `get_bye_weeks` — Team or league-wide bye weeks.
- `get_upcoming_games` — Games from an explicit week onward.
- `get_fantasy_schedule_context` — Player fantasy usage plus schedule context.
- `compare_fantasy_context` — Multi-player fantasy schedule context.
- `find_draft_targets` — League-aware draft target search using imported market data.
- `compare_draft_options` — Compare specific players in a league context.
- `get_draft_context` — League settings, recent picks, drafted count, and top available values.
- `get_bye_week_analysis` — Bye-week concentration warnings for selected players.

## Deployment Notes

Set environment variables:

```bash
export ANTHROPIC_API_KEY=sk-...
export ANTHROPIC_MODEL=claude-sonnet-4-20250514
export DATABASE_URL=sqlite:///./data/superagent_product.db
export SECRET_KEY=change-me-to-a-long-random-secret
export ADMIN_TOKEN=change-me-to-a-random-admin-token
export TOKEN_EXPIRY_DAYS=30
export RATE_LIMIT_PER_HOUR=100
export HOST=127.0.0.1
export PORT=8000
```

For PostgreSQL:

```bash
export DATABASE_URL=postgresql://user:password@host:5432/superagent
```

Start the server:

```bash
python -m superagent.api
```

For production, put it behind a reverse proxy, configure CORS for your domain, use a strong `SECRET_KEY`, and set request limits appropriate to your plan tiers.
