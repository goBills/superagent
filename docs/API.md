# Superagent API Reference

Superagent exposes a small FastAPI service for browser and API demos. It wraps the same Claude tool-calling agent used by the CLI.

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

## Endpoint: POST /chat

Ask a natural-language question and get a research answer with tool transparency.

### Request

```json
{
  "question": "What's Josh Allen's EPA per play in 2024?",
  "session_id": "optional-uuid-for-multi-turn"
}
```

Fields:
- `question` (required, string): Natural-language NFL research question.
- `session_id` (optional, string): Conversation ID for short-term memory across requests.

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
- `session_id` (string): Conversation ID. Reuse this for follow-up questions.
- `error` (string or null): Error message when `ok` is false.

### Error Responses

Empty questions return HTTP 400:

```json
{
  "detail": "Question cannot be empty"
}
```

Missing API keys return HTTP 200 with an error payload so the web UI can display setup guidance:

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
  -d '{"question": "What is Josh Allen'\''s EPA per play in 2024?"}'
```

Multi-turn conversation:

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "Tell me about Josh Allen in 2024"}'
```

Use the `session_id` from the first response:

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "question": "How did he compare to Lamar Jackson?",
    "session_id": "550e8400-e29b-41d4-a716-446655440000"
  }'
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

## Deployment Notes

Set environment variables:

```bash
export ANTHROPIC_API_KEY=sk-...
export ANTHROPIC_MODEL=claude-sonnet-4-20250514
```

Start the server:

```bash
python -m superagent.api
```

The server listens on `http://localhost:8000`. For production, put it behind a reverse proxy, configure CORS for your domain, and add authentication/rate limits.
