# Superagent Value Model — design plan

**Owner of design/validation/UX:** Claude · **Owner of data pipeline/compute/tests:** Codex · **Status:** Planning (2026-05-28)

The proprietary "expected value" signal that replaces a licensed ECR (we parked FantasyPros for commercial-licensing reasons). It is the second signal that, compared against **Sleeper ADP (the market)**, produces the value/faller signal — and it's IP we own, built from data we own.

> **Guiding principle:** a crude metric is *worse* than trusting ADP. This does not drive the board until it **beats or matches ADP in backtest**. Until then it's a secondary "value lens," not the ranking.

---

## 1. The metric: Value Over Replacement (VOR), projection-based

For each player: **project 2026 fantasy points**, then **VOR = projected_points − replacement_baseline(position, league settings)**. Rank all players by VOR → `superagent_rank`.

- **Why VOR, not raw points or raw rank:** it normalizes cross-position scarcity (why an elite TE/QB can outrank a mid RB). Replacement baseline = expected points of the last startable player at that position for the league (12-team 1-QB → QB ~12–15, RB ~30, etc.). We already have `num_teams` / `roster_spots` / `superflex`, so the baseline is league-settings-aware. VOR is the established value-based-drafting foundation — grounded, explainable, ours to compute.

## 2. Inputs (all already in our DuckDB — grounded)

| Need | Source (table.cols) |
|---|---|
| Production basis | `weekly.fantasy_points_ppr`, passing/rushing/receiving lines, `*_epa` (2020–24; 2025 pbp-derived via `plays`/`player_season_stats`) |
| Opportunity (sticky) | `weekly.target_share`, `air_yards_share`, `wopr`, `carries`, `targets` |
| Age curve | `rosters.birth_date` → age, `rosters.years_exp` |
| Rookie draft capital | `rosters.draft_number`, `draft_club`, `rookie_year`, `entry_year` |
| Role / landing spot | `rosters.depth_chart_position` (+ Sleeper current context) |
| Team environment | `team_week_epa`, `game_team_summary` (offensive/defensive EPA) |
| Market (compare against) | Sleeper ADP — `DraftPlayerMarket(source="sleeper_adp", season=2026)` |

## 3. Projection model

**Established players (have NFL history):**
- **Opportunity-weighted production** — fantasy points follow volume more than efficiency. Blend recency-weighted `fantasy_points_ppr`/game (last 1–2 seasons) regressed toward a position/role mean, anchored by sticky opportunity (`wopr`, `target_share` for pass-catchers; carry share + routes for RB; dropbacks/attempts for QB).
- **Adjustments (modest, evidence-based only):**
  - **Age curve** by position (RB decline ~27+, WR peak ~25–29, QB/TE longer) — a multiplier.
  - **Role/team change** from current context (`current_team_differs`, `depth_chart_position`) — only conservative, evidence-based role shifts (starter vs backup). **No speculative "new scheme will boost him"** — reuse the narrative guard.
  - **Games-played expectation** from `injury_status` + durability history.

**Rookies (cold-start — no NFL history):**
- **Draft capital is the #1 rookie predictor.** Fit a `draft_number → rookie fantasy points` curve **per position, on our own 2020–24 rookie classes** (`rosters.draft_number` joined to that player's rookie-season `weekly` output). This is self-calibrated from data we own.
- Adjust by **landing spot/role** (`depth_chart_position`). MVP rookie projection = f(draft_number, position, role). Honest: rookies are market-anchored where our basis is thin.

## 4. Board integration

- Compute `projected_points_ppr`, `vor`, `superagent_rank` per player for 2026.
- **Storage:** write a market-style row `DraftPlayerMarket(source="superagent_value", season=2026)` carrying our rank/projection, so the existing board-merge picks it up (or add `projected_points`/`vor`/`superagent_rank` to the merged row — Codex's call).
- **Value signal:** `value_delta = sleeper_adp − superagent_rank`. Positive = market drafting them later than our value → **Value/sleeper**; negative = market reaching → **Reach/fade**. This replaces today's placeholder `value_delta`.
- **Default board ordering stays ADP** (market-trusted) until the metric is backtested-strong; `superagent_rank` drives `value_delta` + Value/Reach badges. Later: optional "Market ADP ↔ Superagent Value" toggle.

## 5. Validation — the quality bar (gates everything)

- **Backtest harness:** compute the metric for season N using only data ≤ N−1; score `superagent_rank` against actual season-N fantasy finish. Run 2022, 2023, 2024.
- **Metrics:** rank correlation (Spearman) vs actual; top-N hit rate (e.g., our top-24 RB vs actual top-24); and **value-pick precision** — did our positive-`value_delta` players actually beat their ADP cost?
- **Bar:** must correlate with actual finish **at least as well as ADP did** (the market is efficient — ADP is a strong baseline). If it can't match ADP overall → keep ADP as the spine, surface ours only as a value lens. **Ship the backtest numbers; don't hand-wave.**

## 6. Risks & guards

- Crude metric worse than ADP → **backtest gate before it drives anything.**
- Over-speculation on situations → evidence-based adjustments only; narrative guard on the agent's explanations.
- 2025 is pbp-derived (weekly stops at 2024) → derive 2025 features from `plays`/`player_season_stats` consistently.
- Don't override market ordering until proven.

## 7. Division of labor

**Claude:** this design; VOR/replacement math + league-settings awareness; age-curve + draft-capital curve definitions; validation criteria + reviewing backtest results; cockpit UX for value (`value_delta` display, Value/Reach badges); the agent's grounded, narrative-guarded explanation of *why* a player is value.

**Codex:** feature pipeline (extract per-player features from `weekly`/`plays`/`rosters`); implement projection→VOR→rank as a deterministic job; write results to the board (market row/columns); the backtest harness mechanics; tests.

**Shared:** calibrating curves on historical data; agreeing the board-merge contract.

## 7.5 Validation spike result (2026-05-28) — READ THIS

Ran Phase-1 cheaply (Claude, read-only): projected 2025 from 2020–24 `weekly` (recency-weighted PPR/game → positional VOR), scored vs **actual 2025 finish** and vs the **2025 DraftSheets ADP** (the real preseason market we have stored). Set = 144 established players both cover (48 rookies/no-history excluded).

| Predictor | Spearman vs actual 2025 | Top-24 hits | Top-40 hits |
|---|---|---|---|
| **ADP (market)** | **0.405** | 11/24 | 19/40 |
| Crude VOR projection | 0.268 | 11/24 | 17/40 |

**Finding: a naive production projection does not beat ADP — the market is efficient.** Ties on the elite top-24; loses on broader ordering. **Do NOT ship a projection as the board spine.** Two honest paths from here:
- **(A) Iterate the model** — add opportunity weighting (`wopr`/`target_share`), regression-to-mean, age curves, games/injury expectation, and re-backtest across 2022–24. *Might* beat ADP; real work, uncertain payoff (beating an efficient market is genuinely hard).
- **(B) Pivot the IP (recommended)** — keep **ADP as the board spine** (it's the best ranking), and make our owned-data edge the **context + divergence lens + agentic reasoning**, not a replacement ranking: VOR for roster-construction/positional-scarcity decisions, confidence-gated value flags where our usage/EPA read materially diverges from ADP, and the agent's grounded "why." This plays to our actual edge (data + an agent to explain it) without needing to out-predict the market.

## DECISION (Rob, 2026-05-28): Pivot (B) — context layer, NOT a replacement ranking

**ADP stays the board spine.** We do not try to out-rank an efficient market. Our owned-data IP is the layer ADP can't provide. Sections 1–6 (the VOR/projection methodology) remain valid as an *input* to the items below — not as the board ordering.

### What we build (three deliverables)

1. **Roster-construction VOR / positional scarcity.** Use projected-points-over-replacement to answer roster decisions — "is this the last elite TE/QB tier?", "what does waiting cost?" — *without* reordering the board. Surfaces as tier-cliff / scarcity context, not a rank.
2. **Confidence-gated divergence flags.** Where our usage/EPA/opportunity read (`wopr`, `target_share`, EPA trend, role) materially and *confidently* disagrees with ADP, flag **Value** (market sleeping) or **Reach** (market ahead of the tape). **Gated** — only high-confidence divergences surface, because our overall rank is noisier than ADP; we must not spray low-quality flags. (Needs its own mini-backtest: do our flagged "values" actually beat their ADP? Gate the threshold on that.)
3. **Agentic grounded explanation.** The agent explains *why* a player is a value/reach in concrete terms (usage trend, EPA, age, role, scarcity) — within the existing narrative guard. **This is the core differentiator** — nobody with a static ranking sheet has an agent that reasons over the tape.

### Division of labor (pivoted)
- **Claude:** divergence/confidence logic (tool-logic), the gating threshold + its mini-backtest, cockpit surfacing (Value/Reach badges, scarcity/tier-cliff context in the detail panel), the agent explanation layer (tool + prompt, narrative-guarded).
- **Codex:** the feature pipeline (per-player usage/EPA trend + VOR inputs from `weekly`/`plays`/`rosters`), exposing those features on the board row, tests.
- **Shared:** the feature/row contract.

### Phased build
1. **Divergence sensibility check (Claude, next, read-only):** compute our usage/EPA-based value vs ADP for established players; do the top divergences point at *sensible* names, and did flagged "values" beat their ADP in 2025? Sets the confidence gate. **Gate: flags are sensible, not noise.**
2. **Feature pipeline (Codex):** usage/EPA trend + VOR inputs on the board row.
3. **Surface (Claude):** Value/Reach badges (gated) + scarcity context + agent "why."

Board stays ADP-ordered throughout. No "Superagent rankings beat the market" claim — the pitch is *grounded context + an analyst that explains it.*
