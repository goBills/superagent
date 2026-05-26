# Superagent Development: Rob + Claude + Codex

**Status:** Active
**Last Updated:** 2026-05-25
**Product:** Fantasy football decision-support tool (draft + research), not just NFL research.
**Live:** https://superagent-ph31.onrender.com
**Latest commit:** `9ede077` (v0.5.13) · **Tests:** 262 passing · **Repo:** `goBills/superagent`

> Keep this file in sync with reality. If how we work or where we are changes, update it and commit. "Always have context."

---

## Who Does What

| Person | Role |
|--------|------|
| **Rob** | Product owner. Runs live mock-draft testing, surfaces real-world gaps, makes the final call on scope/priority. The "is this actually usable?" voice. |
| **Codex** | Repo engineer. Works directly in the repo (read/edit/test/commit/push), owns deeper backend/data work, runs the full suite, and **owns version tagging**. |
| **Claude** | Reviewer / second brain **and** hands-on fixer. Challenges scope and architecture, spots product implications — and also ships direct fixes (especially UI and tool-logic bugs), verifying before pushing. Both Claude and Codex push to `main`. |

This is a **peer model**, not a strict handoff. Whoever is best positioned does the work. The earlier "Codex implements, Claude reviews" split has evolved: both edit/commit/push. The differentiator is verification discipline (below), not territory.

### Verification discipline (how we avoid shipping broken work)

- **Claude** verifies before pushing:
  - Logic/backend changes → spin up a throwaway venv (`python3 -m venv .verify_venv`), run `pytest -q`, then **remove the venv before committing**.
  - UI changes → render the static frontend in a headless browser (Claude Preview / a local `http.server`), screenshot the actual states, confirm behavior — not just eyeball the CSS. Reproduce the user's exact scenario where possible.
  - Don't trust a summary of a change; check the running behavior.
- **Codex** independently re-runs the full suite, sanity-checks architecture, and tags the version.
- **Trust but verify:** an agent's commit message says what it *intended*; the diff and the running app say what it *did*.

---

## Operational Facts (read before deploying/debugging)

- **Two copies on disk.** `~/Documents/Football AI Project` is the **live git repo** (remote `goBills/superagent`, what Render deploys). `~/Desktop/Football AI Project` is the session's working directory but is **not** the git repo — always edit/commit in the Documents copy.
- **Render Free rebuilds the 366 MB DuckDB on every deploy** (v0.5.3 moved NFL data prep into the build step so Uvicorn opens its port fast). Expect ~3–4 min deploys. Build OOM/timeout would show in the **build** log, not runtime.
- **Product data persists in PostgreSQL** on Render (users, sessions, leagues, draft picks, market data). The NFL analytics live in DuckDB (rebuilt per deploy unless a persistent disk is attached — Free can't). Local dev uses SQLite for the product DB.
- **Confirming a deploy is live:** `/health` includes the deployed git commit. Use `curl -s <url>/health` and compare `commit` with the pushed SHA.
- **Name resolution is the hot path.** `resolve_to_canonical` falls back to a full alias-table scan + fuzzy match + N+1 queries when a name isn't an exact alias — slow on Render Free. Prefer full names and bulk/batched paths over per-row resolution.

---

## Changelog (recent)

| Version | Commit | What |
|---------|--------|------|
| v0.5.13 | `9ede077` | Stops presenting stale market/team data as confirmed 2026 current team context. |
| v0.5.12 | `d22829c` | Makes value/faller queries pick-aware via shared pick-window logic. |
| v0.5.11 | `2153630` | Prompt guardrail against hallucinated player narratives, career stage, injuries, role/news speculation. |
| v0.5.10 | `dd25556` | Hardened bulk paste: name fallback exclusion, summary, `/health.commit`, release checklist. |
| v0.5.9 | `ef276e0` | Draft Room → elegant right-side slide-out drawer (chat no longer crushed); agent frames answers as upcoming **2026** draft prep (2025 ADP/ECR as proxy). |
| v0.5.8 | `d6bf151` | Paste-the-board bulk draft capture: `POST /draft/picks/bulk` + client-side parser for mock-sim format (full names → fast exact-match). |
| v0.5.7 | `d959f11` | Fallen-elite fix: next-pick BPA no longer uses `current_pick` as a lower bound; upper window keeps the pool realistic. |
| v0.5.6 | `7b07248` | Collapsible Draft Room / Examples (superseded by v0.5.9 drawer). |
| v0.5.5 | `5ead6ec` | Recommendations rank best-player-available, not value-delta sleepers (`sort_by`). |
| v0.5.4 | `ecd19c5` | Free-text draft questions auto-inherit league/season/board context. |
| ≤ v0.5.3 | — | Render build-step DuckDB, draft tracker, compact board, 2026 bye weeks, draft tools, canonical identity (Phase 10A–10D). |

**Tagging status:** Codex has tagged through v0.5.11. v0.5.12 (`d22829c`) and v0.5.13 (`9ede077`) still need tag review.

---

## Current Context Workstream (Sleeper)

**Why:** Live mock testing exposed the same root limitation repeatedly: 2025 roster/market data cannot safely answer 2026-current questions about team, age, years of experience, career stage, injury, or role. Prompt guardrails help, but the real fix is a provider-backed current-context layer.

**Source decision:** Use Sleeper as the first current-context provider. Sleeper does **not** replace Superagent canonical identity; it maps into it.

**Layer 1: identity mapping**
- Reuse `external_player_mappings` with `source="sleeper"`.
- Primary mapping is the nflverse roster crosswalk: `rosters.sleeper_id` + `rosters.gsis_id` → `CanonicalPlayer.nflverse_player_id`.
- Fallback is exact normalized name + position.
- Ambiguous name matches go to `needs_review`.

**Layer 2: current context table**
- Store provider state in `player_current_contexts`.
- `canonical_player_id` is nullable so unmapped provider rows are retained.
- Store team, position, age, birth_date, years_exp, entry_year, rookie_year, injury_status, status, depth_chart_position, raw_data, and `updated_at`.
- Treat `team=NULL` as a signal: free agent / unsigned per Sleeper, not missing data.

**Layer 3: refresh path**
- CLI: `python -m superagent.data.refresh_sleeper_context --season 2026`.
- Admin endpoint: `POST /admin/refresh-sleeper-context?token=...&season=2026`.
- Endpoint runs as an admin background job for Render Free.

**Division of labor**
- Codex owns layers 1–3: schema/model, refresh service/CLI, admin endpoint, data-layer tests.
- Claude owns the next integration after schema lands: Evans TB→SF and BTJ years_exp behavior tests, draft tool output fields (`current_team`, `years_exp`, `age`, `context_updated_at`), and agent prompt updates making current context the authority.
- Do not build a separate one-off nflverse age/experience exposure. Use current context as the unified path, with nflverse roster fields as query-time fallback when provider context is missing.

---

## Roadmap & Open Items

**Logged (captured as task chips, not yet built):**
- **Current-age filtering** ("elite players aged 25–27 in their prime"). Age is *not* a live-data problem — `birth_date` is already stored on `CanonicalPlayer`; it's just never exposed. Compute age as-of-season and surface it in draft/player outputs.
- **Tap-to-draft from a ranked list** — the eventual gold-standard capture method (tap a player to mark drafted, no typing, no server-side resolution). Paste-the-board (v0.5.8) is the interim solution.

**Deferred — Phase 7B (pending Rob's ESPN league activation):**
- Live injuries, depth charts, current-roster / 2026 team moves. We only have 2020–2025 data + 2025 market snapshot + 2026 official bye weeks. Be transparent about this.

**Watch:** recommendation quality now depends heavily on DraftSheets ADP/avg-rank coverage for the top players. If top recs look off, suspect import data gaps before ranking logic (v0.5.5/v0.5.7 verified the logic).

---

## Communication Protocol

**Finding a bug:** identify + prioritize (blocking/high/low) → state symptom, root cause, proposed fix → implement + test if blocking → commit with a "why" message.

**Completing work:** note what was built + tests passed + commit hash → tag the version (Codex) → the other reviews.

**Disagreement:** state the issue as "because X, Y risk" (not "this is wrong") → propose an alternative → accept the better argument, not ego → document the decision here or in the commit.

**Cross-agent updates:** when Claude or Codex finishes a batch, write a short, copy-pasteable summary for the other (commit SHAs, what changed, what to verify, tags needed).

---

## Definition of Done

✅ Code written/fixed · ✅ Full suite passes (not just new tests) · ✅ Clean commit (explains *why*) · ✅ No security holes (auth, validation, rate limits) · ✅ Verified by running the app/tests (not self-attested) · ✅ Docs updated when behavior changes · ✅ Version tagged · ✅ Deploy confirmed live

## Release Checklist (per version)

1. Full suite green locally (`pytest -q`).
2. For UI changes: render the actual states in a browser and confirm behavior.
3. Commit with a "why" message; push to `main`.
4. Tag the version (Codex) → `git tag vX.Y.Z <sha> && git push --tags`.
5. Confirm the deploy: `curl -s <url>/health` → check `commit` matches the pushed SHA.
6. For draft/data features: run **one real mock draft** against the live build before building the next thing.

---

## Principles

1. **Build deterministic tools first** — the AI is only as good as the data underneath; never ship fuzzy matching without verification.
2. **Ship small, iterate fast** — incremental versions, merge early, don't hoard fixes in branches.
3. **Artisan quality** — production code from day one; don't skip error handling for convenience.
4. **Transparent about limitations** — tell users what we don't have (injuries, live data, predictions); let data speak, don't hallucinate.
5. **Verify against reality** — cross-check vs ESPN/NFL.com, test with real data, run the actual app. If it breaks in production, we own it.
6. **Usable under pressure** — for the draft tools especially: if it can't keep pace with a live draft, it isn't done.

---

## Questions or Changes?

Update this file and commit to `main`. Keep it in sync with reality.
