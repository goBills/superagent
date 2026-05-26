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
| v0.10.0 | `8c611d7` | (Claude) Top-level workspace switch (Draft live; Roster/Waivers "Coming soon"; Trade disabled); reset moved into the live-capture bar as "🔄 New mock" with a confirmation modal; "Draft Mode" toggle renamed "On the clock"; shell de-emphasizes "draft war room" (Superagent is the permanent brand, draft framing only when Draft is active). |
| v0.9.6 | `d7a3312` | (Claude) Fix false "Team Changed" badge from cross-source team-abbreviation mismatch (JAC vs JAX, LA vs LAR, etc.) via `_normalize_team_code()` in `draft_tools.py`. Real 2026 moves still flag. |
| v0.9.5 | `39e6c60` | (Claude) Clearer pool-shortfall wording: "Ranked pool short by N — X players left for Y remaining picks" (units were ambiguous). |
| v0.9.4 | `1c3adb2` | (Codex) Draft sheet pool metadata + depth rows; richer summary (`total_draft_picks`/`remaining_picks`/`pool_shortfall`), per-row `tier_level`/`current_team`/`age`/`years_exp`/`injury_status`. |
| v0.9.0–0.9.3 | `09f2b5e`–`546d73a` | Guest access + per-user league auto-provision; league-settings-driven cockpit; row-selection draft UX; forward-compat pool warning. |
| v0.8.x | `cd83239`–`e47d2cf` | Cockpit beautification (tier gradients, position pills, brand stripe), labeled fields, Draft Mode paste bar, reset-for-new-mock, full-width board. |
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

### Deploy status (2026-05-26)

**Live and healthy.** `https://superagent-ph31.onrender.com/health` → `200 {"commit":"8c611d72441b"}` (= v0.10.0, latest `main`). Verified end-to-end against production: guest auth provisions a user + league, draft sheet returns 178 ranked rows with Codex's richer summary populated (`pool_shortfall:14` for a 12×16 league), and the v0.10.0 shell (workspace switch, reset modal, "On the clock") is confirmed in the served HTML.

**Resolved crash-loop:** an earlier deploy of this commit crash-looped — `start.sh` logged "NFL DuckDB not found… Downloading…" then "player_stats_2020.parquet — URL not accessible" → `Exited with status 1`. Render retried and the subsequent build succeeded (transient nflverse/GitHub-releases download failure). No code change was needed to recover.

**Fragility flag for Codex (deploy/data owner):** the failing attempt ran the *runtime* bootstrap path (`BOOTSTRAP_NFL_DATA=true` → download at boot), not `render.yaml`'s build-step DuckDB (`buildCommand` runs `fetch_nflverse` + `database`, runtime `BOOTSTRAP_NFL_DATA=false`). That points at the **`Dockerfile` being the live runtime** — it does *not* bake the DuckDB at build time (only `COPY src/`), so any cold start where the nflverse download flakes will exit 1 and crash-loop. Two robust options: (a) make the service use `render.yaml`'s native-python path, or (b) add `RUN python -m superagent.data.fetch_nflverse && python -m superagent.database` to the `Dockerfile` builder so the DB is baked into the image. Left untouched pending Codex — deploy/data is his domain and this overlaps in-flight depth work.

---

## Handoff → Codex (2026-05-26 session)

Division of labor confirmed: **Claude owns frontend/UX + tool-logic; Codex owns backend/data/perf.** Here's everything Claude touched this session and what's now in Codex's court.

### What Claude shipped (all live on `main`, verified)
1. **`draft_tools.py` — `_normalize_team_code()` (v0.9.6, `d7a3312`).** New module-level `_TEAM_CODE_ALIASES` map + helper; `current_team_differs` now compares *normalized* franchise codes so cross-source spelling variants (JAC↔JAX, LA↔LAR, OAK↔LV, SD↔LAC, WSH↔WAS, ARZ↔ARI, BLT↔BAL, CLV↔CLE, HST↔HOU, plus PFR 3-letter forms) don't read as team changes. Real 2026 moves still differ. Additive only — does not touch Codex's `tier_level`/depth code. Regression tests added in `tests/test_draft_decision_tools.py` (`test_normalize_team_code_collapses_franchise_aliases`, `test_current_team_differs_ignores_abbreviation_only_mismatch`).
2. **Pool-warning wording (v0.9.5, `39e6c60`)** and **forward-compat pool warning (v0.9.3)** — frontend consumes `summary.available_count` / `remaining_picks` / `pool_shortfall` (all now populated by Codex's v0.9.4). Working live.
3. **Workspace switch + reset UX + brand (v0.10.0, `8c611d7`)** — frontend-only (`index.html`).

### ⚠️ Correction: the Sleeper current-team data is CORRECT — not a bug
During review, Claude flagged ~27 players whose `current_team` (Sleeper) differs from the nflverse roster team (e.g. Evans TB→SF, Murray ARI→MIN, Moore CHI→BUF) as suspicious. **Rob confirmed these are real 2026 offseason moves.** There is **no data bug** — the current-context layer is working as intended, and the "Team Changed" badge surfacing real moves is the desired signal. Do **not** chase this. (The only genuine false positive was the JAC/JAX *spelling* case, fixed in v0.9.6.)

### Row/sheet contract the frontend now depends on (please keep stable)
The draft-sheet `rows[]` fields the UI reads: `canonical_player_id`, `player_name`, `position`, `team`, `current_team`, `current_context_available`, `current_team_differs`, `bye_week`, `tier`, `tier_level`, `effective_rank`, `rank_source`, `ecr`, `value_delta`, `age`, `years_exp`, `injury_status`, `is_drafted`, `is_mine`, `badges[]`. Summary fields read: `available_count`, `drafted_count`, `remaining_picks`, `pool_shortfall`, `draftable_rank_limit`. Renames/removals here will break the cockpit.

### Open in Codex's lane
- **Pool depth** toward 12×16 (live `pool_shortfall: 14`): deeper bench rows, K support, D/ST / team-defense mapping, unresolved-row review.
- **Bulk-paste perf**: skip unchanged existing picks, resolve only new/changed.
- **Deploy hardening**: the Dockerfile/runtime-bootstrap fragility above.
- **Reset endpoint**: already exists (`DELETE /leagues/{id}/draft/picks`, returns `picks_deleted`); the new modal uses it as-is — only needs tests, not a rebuild.
- **In-season data foundations** (rosters/usage/injuries) to light up the Roster/Waiver "Coming soon" workspaces.

### Naming decision (open for Codex input)
Two concepts were colliding under "Draft Mode." Now: **Workspace** = Draft / Roster / Waivers / Trade (top-level). **"On the clock"** = the live pick-capture toggle *inside* Draft (formerly "Draft Mode"); the paste bar + reset live there. Flag if you'd prefer different labels before they harden.

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
