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
- **Name resolution is the hot path.** `resolve_to_canonical` falls back to a full alias-table scan + fuzzy match + N+1 queries when a name isn't an exact alias. Bulk board paste now uses the v0.13.3 batch resolver for exact market/alias hits; keep misses rare and prefer bulk/batched paths over per-row resolution.
- **Draft data is source/season-specific.** Check the draft sheet response `market_season` + `source` before debugging a missing player or stale rank. The older 2025 board is DraftSheets `8.13.25` (`source=draftsheetsv6`, `season=2025`) and does **not** contain the 2026 rookie class. The 2026 board path is `source=sleeper_adp`, `season=2026`; after that import is live, players like Jeremiyah Love and Carnell Tate should be present.

  **2026 data path (live — Rob has no 2026 DraftSheets file, so we went source-agnostic):** the market layer is already source-agnostic (`DraftPlayerMarket` keys on `(source, season, canonical_player_id)`), so DraftSheets is just *one* ranking source. Split the need: **(a) Identity** — the 2026 player universe (incl. rookies) is solved through **Sleeper** (`/v1/players/nfl` carries 2026 rookies). `refresh_sleeper_context` now seeds current active fantasy players into canonical even when they have no nflverse/DraftSheets row. **(b) Rankings** — Codex evaluated FantasyPros ECR vs Sleeper ADP. **Decision: Sleeper ADP is the MVP source; FantasyPros is parked unless Rob gets explicit commercial permission.** FantasyPros API terms are personal/non-commercial and prohibit building a competing product; scraping around that is the wrong move for a commercial venture. Sleeper's read-only public API is free, and the live 2026 projections payload has clean `adp_ppr` / `adp_half_ppr` / `adp_std` / `adp_2qb` fields with sane 2026 ranks. v0.14.0 adds `DraftPlayerMarket(source="sleeper_adp", season=2026)`. **Prod import run by Codex 2026-05-28:** `source=sleeper_adp`, `season=2026`, `scoring=ppr`, `replace=true`, `min_import_rows=150`, `max_adp=350`; imported 245 market rows from Sleeper projections. **Live smoke verified:** default 12x16 guest league returns `market_season:2026`, `available_count:192`, `remaining_picks:192`, `pool_shortfall:0`; Jeremiyah Love row 20 / ADP 19.7, Carnell Tate row 60 / ADP 62.9, Jordan Love row 119 / ADP 124.8. Note: the synchronous prod identity refresh timed out client-side, but the later ADP import reused 245 existing Sleeper mappings, so the transaction appears to have completed. Use the background job path for future full identity refreshes.

  **Claude independent verification (live `d199dc7`, 2026-05-28):** ✅ `market_season:2026`, 192/192, `pool_shortfall:0`; **Jeremiyah Love (RB/ARI, ADP 19.7) and Carnell Tate (WR/TEN, 62.9) are on the board** with sane ranks; top-10 are legit studs with sane ADP (Bijan 1.4, Gibbs 2.9, Chase 3.4…) — Sleeper ADP is clean, no SDIO-style garbage. **Two gaps found:** **(1) No K and no DST on the 2026 board** (`position=K`→0, `position=DST`→0; pool is RB 61 / WR 72 / TE 33 / QB 26 only), so the K/DST tabs (v0.13.7) render empty and a full 16-roster team can't fill the K/DST slots. **Fix is NOT a new source** (Rob's point): D/ST are franchise entities (no 2025→2026 expansion/relocation/rename) and kickers are a veteran position, so the **2025 K/DST data is still valid for 2026**. Those rows are still in the DB and intact — **10 DST + 11 K at `source=draftsheetsv6, season=2025`**. **Codex task: carry those K/DST rows over into `season=2026`** (copy/promote into the 2026 market, or have the 2026 board fall back to the 2025 K/DST when 2026 has none). Board-composition nuance: a 12×16 = 192 picks includes ~12 K + ~12 DST drafted in the last rounds, so the 2026 pool should reserve late slots for them rather than being 192 skill players + K/DST appended beyond the cap (where they'd never surface). Kicker team may be stale if one changed teams in 2026 FA — the Sleeper current-context layer already corrects `current_team` for display, and late-round ADP precision is negligible, so carry-over is safe. **(2) `ecr` is `None` and `value_delta` looks positional/constant (4.5 RB, 7.5 WR), not per-player** — expected since FantasyPros (the ECR half) is parked, so `effective_rank == adp` and the value/faller signal is degraded. Board ordering by ADP is sound; the *value* signal isn't meaningful yet. **Direction (Rob, 2026-05-28): build our OWN proprietary value metric instead of licensing ECR.** Derive an "expected value" rank from data we own — nflverse production/EPA history + Sleeper current context (age/role/team) — and compare it against Sleeper ADP (the market); the divergence is the value/faller signal, no third party. Strategic win: dodges FantasyPros licensing, differentiates the product, leverages our nflverse + agentic edge. **Caveats:** it's a real modeling build with a quality bar (a crude metric is *worse* than ADP-only), and the 2026 rookie class is a cold-start (no nflverse production history) — they'd need a different basis (draft capital / college). **Naming/branding parked** per Rob. Future Codex+Claude effort (data model + tool-logic), not a quick swap; board runs ADP-only until then.

---

## Changelog (recent)

| Version | Commit | What |
|---------|--------|------|
| v0.14.0 | `08f2858` | (Codex) 2026 source-agnostic board foundation: expanded Sleeper identity seeding and new Sleeper ADP ingester/admin endpoint writing `DraftPlayerMarket(source="sleeper_adp", season=2026)`; live prod import verified full 12x16 pool with Love/Tate on the board. |
| v0.13.6 | `d17108a` | (Codex) Draft sheet rank-gap backfill: all-position sheets no longer treat sparse/gapped ADP values as a pool shortfall; after sorting, the sheet backfills with the next best ranked rows until remaining draft slots are covered. |
| v0.13.5 | `7b039ce` | (Codex) Authoritative DraftSheets replace-mode import: `replace=true` clears only the requested source+season, runs delete+insert in one transaction, and refuses suspiciously small parsed/mapped row counts before commit. |
| v0.13.4 | `c3fc4e5` | (Codex) DraftSheets team-defense import fix: `DST`/`D/ST`/`DEF` rows now map to stable `team_dst_*` canonical IDs with real NFL team codes, avoiding player-name collisions and importing the missing D/ST pool rows. Re-import DraftSheets after deploy to hydrate persisted prod market rows. |
| v0.13.3 | `d46f755` | (Codex) Batch bulk draft-pick resolution: `/draft/picks/bulk` preloads market rows, aliases, and existing board picks once; exact board names resolve in memory, and only misses fall through to the slow fuzzy resolver. |
| v0.13.2 | `3780fde` | (Claude) Chunk large board pastes (10/req) with a live "X/N done" counter — responsive + survives cold-start; small pastes stay one request. |
| v0.13.1 | `7986c4d` | (Codex) Backend defense-in-depth for bulk paste: `/draft/picks/bulk` skips unchanged existing picks before name resolution; identical over-sends no longer hit the resolver, changed same-slot picks still update, and own-pick roster repair still runs. |
| v0.13.0 | `ca55726` | (Claude) Live player search on the board + football working cue. |
| v0.12.2 | `c15b229` | (Claude) Update Board sends only new/changed pasted picks from the client, making whole-board re-paste as fast as one-round paste in the common case. |
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

### Codex priorities (P0 / P1)
- **🔴 ACTIVE (P0) — K/DST on the 2026 board: carry over the stable 2025 rows.** The 2026 board (`source=sleeper_adp`, `season=2026`) has **0 K and 0 DST** (`position=K`→0, `position=DST`→0), so the K/DST tabs (v0.13.7) render empty and a 16-man roster can't fill those slots. **No new source needed** — D/ST are franchises (no 2025→2026 expansion/relocation/rename) and kickers are veterans, so the 2025 rows are still valid and intact: **10 DST + 11 K at `source=draftsheetsv6, season=2025`**. Promote them into `season=2026` (copy into the 2026 market, or have the 2026 sheet fall back to the 2025 K/DST when 2026 has none). **Board-composition:** a 12×16 = 192 picks already includes ~12 K + ~12 DST drafted late, so reserve their late-round slots rather than appending beyond the 192 cap (where they'd never surface). Sleeper current-context corrects any stale kicker team; late-round ADP precision is negligible. **Claude verifies** K/DST appear on the 2026 board afterward.
- **P0 — Bulk-paste perf. DONE in layers.** Re-pasting a growing board reached ~40s late in the draft. *Client half shipped (v0.12.2, `c15b229`):* the frontend diffs the paste against local `draftBoardPicks` and POSTs only new/changed picks. *Backend defense-in-depth shipped (v0.13.1, `7986c4d`):* `/draft/picks/bulk` skips unchanged existing picks before name resolution, so stale clients can over-send safely without re-triggering the slow resolver. *Resolver batching shipped (v0.13.3, `d46f755`):* first full-board paste now preloads draft-market rows, exact aliases, and existing picks once; exact names resolve in memory and only misses use the slow fuzzy resolver. *(Claude verified live on `1f72e331`: a 27-pick clean paste dropped ~6s → 1.5s, 0 fuzzy misses.)* These stack: frontend sends fewer rows; backend skips unchanged over-sends; first-time/new picks avoid per-name table scans. Server-side tests cover identical re-paste skipping resolution, changed same-slot picks still updating, roster repair for own picks, and exact bulk board names bypassing `_resolve_draft_pick_player`.
- **P0 — Pool depth. DONE / LIVE VERIFIED.** v0.13.4 (`c3fc4e5`) maps DraftSheets `DST`/`D/ST`/`DEF` rows to stable `team_dst_*` canonical IDs, sets their real NFL team code for byes, prevents false player collisions (e.g. Dallas Cowboys ≠ Dallas Turner), and marks old pending review rows resolved when a clean re-import maps them. v0.13.5 (`7b039ce`) added safe `replace=true` imports. **Prod import run by Codex 2026-05-28:** `source=draftsheetsv6`, `season=2025`, `sheet=DATA`, `replace=true`, `min_replace_rows=700`; deleted 812 stale markets / 476 pending reviews and imported 844 mapped rows from 966 workbook rows. D/ST is no longer stuck in review. First smoke showed 12×16 improved 178→187 but still short 5 because DraftSheets ADP is sparse/gapped around pick 192; v0.13.6 (`d17108a`) backfills the all-position sheet with the next best ranked rows until remaining draft slots are covered. **Live smoke verified on prod commit `58d58b1`:** default 12×16 guest league returns `available_count:192`, `remaining_picks:192`, `pool_shortfall:0`. *(Claude independently re-verified on current live `bb11773`: `192/192`, `pool_shortfall:0`; 11 team D/ST in the top-192 pool with clean `team_dst_*` IDs/real team codes; no real player displaced by a defense — collision guard held.)*
  - **Authoritative `replace=true` import shipped (v0.13.5, `7b039ce`).** Re-importing a newer workbook no longer leaves stale ghost rows for players that dropped off. Guardrails implemented: (1) delete is scoped to requested `source` + `season`; (2) delete + insert happen in one transaction, so failed imports roll back to the old board; (3) `min_replace_rows` sanity-gates both parsed rows and mapped rows before commit. **Use for prod refresh:** `replace=true&min_replace_rows=700` with `source=draftsheetsv6`, `season=2025`, `sheet=DATA`.
- **P1 — Reset endpoint tests.** Frontend modal uses the existing `DELETE /leagues/{id}/draft/picks` (returns `picks_deleted`); add backend coverage that clearing board/roster/pick state **preserves league settings**. Endpoint exists — needs tests, not a rebuild.
- **P1 — Deploy hardening.** Render bootstrap/build fragility is still real (Dockerfile runtime-bootstrap path, see Deploy status above); **document whether the DuckDB/data bootstrap should stay build-time or move to an async/runtime-safe path.** **Now on Render Standard** — which (unlike Free) **can attach a persistent disk**. Persisting the 366 MB DuckDB on a disk would skip the per-deploy rebuild (faster deploys) and eliminate the runtime-bootstrap crash-loop risk entirely. Worth evaluating, Codex.
- **Future — proprietary value metric → full design plan: [`docs/value_model_plan.md`](docs/value_model_plan.md).** Our own VOR-based "expected value" rank from data we own (nflverse production/`wopr`/EPA + age via `rosters.birth_date` + **rookie draft capital via `rosters.draft_number`**) compared against Sleeper ADP → the value/faller signal. Dodges FantasyPros licensing, differentiates the product. **Gated on a backtest beating/matching ADP** before it drives the board. Claude owns design/validation/UX; Codex owns the feature pipeline/compute/tests (coordinate with the existing `draft_value.adjust_draft_value`). Phased: pipeline-proof → depth (age + rookie draft-capital curve) → cockpit surface. Naming parked. Board is ADP-only until it clears the bar.
- **Later — In-season data foundations** (rosters/usage/injuries) to light up the Roster/Waiver "Coming soon" workspaces. **DECISION (Rob, 2026-05-27): not paying for SportsDataIO — it's parked.** The trial scrambles injuries *and* projections, so it adds nothing over what we have. Build in-season on **Sleeper (injuries/team/age — already in the current-context layer) + nflverse (usage/stats) + DraftSheets (ranks) + `official_bye_weeks` (byes)**. Keep the read-only SDIO probe/client/tests in the repo (harmless, documents access) but **don't build persistence/crosswalk on it** unless we ever pay. *SportsDataIO spike done (Codex, `d99368a`, read-only, 5/5 endpoints).* **Product guardrails (kept for the record):**
  - **SDIO is an in-season data source, NOT a draft-rank source.** Its projection ADP/PPR-ADP fields look wrong for top players and need semantic inspection (scale? format? stale?). **DraftSheets ECR/ADP stays the canonical ranking source** — do not feed SDIO ADP into the draft sheet's `effective_rank`.
  - **SDIO's real value = depth charts (32 teams) + season projections (742) + byes** → the Roster/Waiver building blocks. Byes can cross-check `official_bye_weeks.py`.
  - **Trial masks injuries (`"Scrambled"`).** The Roster/Waiver placeholders promise injury flags; SDIO can't back that on the trial. **Sleeper already supplies `injury_status`** in the current-context layer — keep Sleeper as the injury source; let SDIO own depth/projections/usage. Confirm paid-tier injury coverage before committing.
  - **Identity:** SDIO `PlayerID` (6,200) needs a canonical crosswalk like Sleeper (`external_player_mappings`, `source="sportsdataio"`) — prefer a stable ID join (GSIS/PFR if SDIO exposes one) over name+position. Mark all SDIO state as current-season, never conflated with 2025 nflverse historicals.
  - **Concrete trial findings (Claude ran the probe 2026-05-27, season 2026):** Only **byes (clean, real: CAR/KC wk5, CIN wk6…) and depth charts (per-team offense/defense) are usable on the trial.** **Projections are degraded, not just injuries:** `AverageDraftPosition` reads **0.2 / 0.4 / 0.6** for Bijan/Gibbs/Chase (not pick numbers) and `FantasyPoints` look low-scale (~119 for a top RB) — the trial appears to scramble/scale projection values too. Injuries confirmed masked (`InjuryStatus`/`InjuryBodyPart`/`InjuryNotes` = `"Scrambled"`). **Crosswalk risk:** the Players feed exposes only SDIO's own `PlayerID` in the sample — no GSIS/PFR/Sleeper id in the first 30 keys, so mapping is name+position-fragile unless a deeper field carries a real ID (Codex: verify full schema). **Net: a paid tier is required before SDIO can power injuries OR projections; byes/depth charts are the only trial-usable feeds.**

### Release hygiene (we've had version confusion)
- **Tags now exist** for the three shipped this session (created + pushed 2026-05-26): `v0.9.5` → `39e6c60`, `v0.9.6` → `d7a3312`, `v0.10.0` → `8c611d7`. Existing tags are lightweight, styled `vX.Y.Z: <subject>`.
- **Gap to backfill (Codex):** `v0.8.x` and `v0.9.0–v0.9.3` are untagged (tags jump `v0.7.0` → `v0.9.4`). Backfill if we want a clean history.
- **Always include exact commit hashes** for any version referenced in a handoff.
- **After every deploy, confirm `/health` reports the expected commit before QA.** If Render shows a failed/intermediate deploy, do **not** assume failure until `/health` is checked — this session's "crash-loop" had already self-recovered and was serving the right commit.

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
