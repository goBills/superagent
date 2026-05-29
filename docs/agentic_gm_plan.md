# Agentic GM — design plan & labor split (PROPOSAL for Codex review)

**Authors:** Claude (draft) → Codex (review/agree) → Rob (greenlight) · **Status:** Codex-reviewed proposal, awaiting Rob greenlight, 2026-05-29
**Origin:** First outside user (Salam) + Rob: post-draft engagement is dead; an agentic co-manager "two weeks ahead," with **trades as the hero feature**, is the wedge vs Yahoo/ESPN/Sleeper (which just repackage generic blurbs).

> This is a proposal. Codex: please react inline — agree, push back, or re-scope the split. Goal we both sign up to: **make this the best fantasy tool, not just a draft toy.** Nothing here ships until we agree the split and Rob greenlights.

---

## 1. The wedge (why this wins)

Incumbents do generic, one-size player blurbs and a dead post-draft experience. Our edge is **league-specific reasoning**: we already know *every team's roster* in a league, we have production/usage history + current context, and we have an agent that can reason and explain. So we can answer the things no incumbent does:
- **Who should I trade for / away** — given *my* roster and *the other 11*.
- **Who's stacked** at a position and can afford to deal a player; **whose stock is up/down**.
- **How to construct + pitch the deal** so it actually gets accepted. "Make trades fun."

Trades are the hero because they're the highest-effort, highest-avoidance task: *"nobody has the time to study everyone's roster, or the nerve to make the deal."* That's exactly what an agent removes.

## 2. What we already have (makes this uniquely doable)

| Asset | Status | Why it matters for trades |
|---|---|---|
| **All teams' rosters** | ✅ Live — every `LeagueDraftPick` carries `fantasy_team_name` (indexed) | We can reconstruct *every* team's roster from the board. This is the foundation trades need, and we already capture it. |
| Canonical identity + Sleeper current context | ✅ Live | team/age/injury/role per player |
| nflverse production/usage (2020–25: `wopr`, target share, EPA) | ✅ Live | the basis for "stock up/down" |
| Value layer (VOR + ADP-divergence) | ⏳ Designed, parked (`docs/value_model_plan.md`) | V1 trade value/scarcity context comes from here; live "stock up/down" becomes a v2 extension once weekly data exists and validates. |
| Agent + tool framework + narrative guard | ✅ Live | generate + explain + pitch deals, grounded |
| Workspace shell (Trade tab exists, disabled) | ✅ Live | a home for it |

**Key realization:** the parked value layer and Trade Mode are the same project viewed from two ends. Trade Mode is *why* the value signal matters. We should build the value/context signal **in service of trades**, not as an abstract ranking.

## 3. The honest constraint: season timing

"Two weeks ahead" / "whose stock is up" in the live sense needs **in-season weekly data** (recent usage, role changes, injuries, upcoming schedule) — which doesn't exist until the 2026 season starts (Sept 2026). So split the ambition:

- **Trade Mode v1 — buildable NOW (draft/preseason):** cross-roster surplus/need matching + value-based buy/sell using **ADP/effective rank + VOR/scarcity + roster construction**. Fully demoable today on any drafted league. This proves the engine and the UX.
- **Trade Mode v2 — live season (Sept 2026+):** layer weekly usage/EPA trends, injuries, schedule strength → real "stock up/down" + "two weeks ahead." Gated on the in-season data foundation (Sleeper + nflverse weekly) and roster freshness (adds/drops).

We build v1 now; v2 slots in when the season + data arrive. Don't block v1 on live data.

## 4. The trade engine (the core IP)

A deterministic pipeline (tools), with the agent reasoning on top:

1. **Roster reconstruction** — build every team's roster from `LeagueDraftPick` (+ later, in-season adds/drops). Per team: players by position, with value (VOR) + current context.
2. **Surplus / need detection** — per team, compare roster vs starter requirements + replacement value → who's *stacked* (tradeable surplus) and who's *thin* (need). (Reuses roster-construction logic.)
3. **Complementary matching** — find team pairs whose surplus/need are inverse (I'm RB-stacked/WR-thin; they're the opposite). These are the natural trade partners.
4. **Candidate deal generation** — propose concrete swaps across a matched pair (my RB3 ↔ their WR2), optionally multi-player to balance value.
5. **Fairness + mutual-benefit scoring** — does the deal improve *both* teams' roster shape / lineup value? A good trade is win-win, not a fleece (fleeces don't get accepted — and "make trades fun" means deals that actually happen).
6. **Agent rationale + pitch** — the agent explains *why* (the value/need logic) and *how to pitch it* to the other manager, grounded + narrative-guarded. This is the differentiator users feel.

## 5. UX — Trade Mode workspace (Claude)

The disabled "Trade" tab becomes live. Shape (subject to iteration):
- **"Trade finder"** — given my team, surface the top few *mutually beneficial* deals across the league, each as a card: give X / get Y, why it helps me, why they'd say yes, the pitch.
- **Target a specific player or team** — "what would it take to get [player]?" / "who should I target on [team]?"
- **Trade evaluator** — paste/propose any deal → fairness + lineup-impact read.
- All grounded in the agent's "why," consistent with the draft cockpit's feel (board = map, agent = scout).

## 6. Division of labor (PROPOSAL — Codex please confirm/adjust)

### Codex review / adjustments (2026-05-29)

Codex agrees with the wedge and the v1/v2 split. Two adjustments before build:

1. **Do not call v1 a stock engine.** v1 is a league-specific trade-fit engine using market value (Sleeper ADP/effective rank), roster construction, scarcity, byes, and current context. Predictive "stock up/down" only becomes a first-class field after we have in-season usage/injury/schedule trend data and a validation gate.
2. **Put the stable backend contract before the matching UX.** Claude can own the trade-matching algorithm/UI, but the input contract needs to be deterministic, versioned, and test-covered. The engine should consume a `TradeContext` payload, not ad hoc draft-sheet rows.

Codex accepts ownership of:
- Reusable all-team roster reconstruction from `LeagueDraftPick` now, with a later source-precedence path for synced `LeagueRosterPlayer` data.
- Player value/context feature payloads used by trades.
- Authenticated API/tool surfaces and backend tests for roster/value correctness.

Codex suggests sharing fairness ownership: Claude owns the product feel and matching heuristics; Codex should review/test any numeric fairness helper that becomes backend-contractual, because small scoring bugs will create obviously bad trade suggestions.

## 6.5 Value Contract (Codex proposal)

Trade Mode v1 should consume one stable payload:

```text
TradeContext
  league_id, season, market_source, roster_source, roster_freshness
  settings: num_teams, roster_spots, QB/RB/WR/TE/FLEX/SF/bench/scoring
  teams[]:
    fantasy_team_name
    pick_count
    counts_by_position
    needs_by_position
    surplus_by_position
    players[]
  unresolved_players[]
```

Each `players[]` item should expose:

```text
PlayerTradeValue
  canonical_player_id
  player_name
  position
  team
  current_team
  bye_week
  age
  years_exp
  injury_status
  adp
  effective_rank
  rank_source
  position_rank
  tier
  trade_value_score        # deterministic 0-100 market/roster value, not a prediction claim
  roster_role              # starter, flex, bench, surplus
  team_need_fit            # how much this player matters to his current roster
  data_quality             # complete, missing_context, unresolved, stale_roster
  flags[]                  # injury, bye_cluster, current_context_missing, team_changed, etc.
```

Fields explicitly **not** in v1:
- `stock_score`
- `stock_trend`
- `two_week_outlook`
- unvalidated projection rank that competes with ADP

Those are v2 fields gated on live weekly inputs. For v1, recommendations should explain themselves as "market value + roster leverage," not "our model knows his stock is rising."

### Fairness contract for v1

A candidate trade is eligible only if:
- both sides stay roster-legal after the swap,
- the receiving team gets help at a need or flex-depth weakness,
- the sending team is dealing from surplus,
- market-value gap is within an agreed tolerance, and
- the pitch can truthfully state why the other manager benefits.

The first numerical pass can use `trade_value_score` plus roster-fit deltas. If the score says a deal is fair but the explanation would sound dishonest, the deal fails product review.

**Claude owns (UX + tool-logic + reasoning):**
- Trade Mode workspace UI (finder/target/evaluator, deal cards, pitch display).
- The trade-matching tool-logic: surplus/need → complementary pairing → candidate generation → fairness scoring (the algorithm).
- Agent tooling + prompts for trade rationale & pitch, narrative-guarded.
- Validation: do generated deals look sane to a human (the "would a real manager propose this?" check).

**Codex owns (data + pipeline + perf + tests):**
- Roster reconstruction from picks as a reusable backend primitive (all teams), and keeping it fresh later (in-season adds/drops, league sync).
- The value/context feature pipeline (market value + scarcity now; usage/EPA trends later) that the trade engine consumes (this is the `value_model_plan.md` work, now scoped *for trades*).
- In-season data foundation when the season starts (weekly usage/injuries/schedule) for v2.
- API endpoints the Trade UI calls; tests for roster/value correctness, plus shared review of any backend fairness-scoring helper.

**Shared (agree before building):**
- The **value contract** — what fields the trade engine consumes (market rank, VOR/scarcity, 0–100 trade value, future stock fields). This is the seam between Codex's value pipeline and Claude's matching logic. Define it first.
- Roster-freshness model (draft-only v1 vs synced v2).
- Fairness definition (what "mutually beneficial" means numerically).

## 7. Sequencing (proposal)

1. **Agree this plan + the value contract** (Claude + Codex) — the one true dependency.
2. **Codex:** roster-reconstruction primitive (all teams from picks) + v1 `TradeContext` / `PlayerTradeValue` fields (start simple: market value + roster/scarcity context; no stock claim yet).
3. **Claude:** trade-matching tool-logic on top of that (surplus/need → pairs → candidate deals → fairness), behind a tool.
4. **Claude:** Trade Mode UI (finder first — the wow moment) + agent pitch.
5. **Iterate with Rob** on real drafted leagues; **v2 live-season** layer when the season + weekly data land.

## 8. Risks / open questions (for Codex + Rob)

- **Value quality gates trade quality.** A bad predictive signal → bad trades. We already learned (value_model_plan backtest) that beating ADP is hard — so v1 leans on ADP + VOR/scarcity + roster fit (defensible) and only adds predictive "stock" once it backtests. Agree we don't ship trade recommendations built on an unvalidated signal.
- **Roster freshness** — v1 is draft-state accurate; mid-season it's stale without adds/drops. Do we require a league sync (Sleeper API) for v2, or manual update? (Salam also asked for Yahoo/Sleeper league API — this is where it pays off.)
- **Scope of v1** — is preseason trade-finder compelling enough to demo to friends now, or do we wait for live-season signal? (Claude's view: v1 proves the engine + UX and is a strong demo; build it.)
- **"Make it fun"** — is the win a slick finder UI, a weekly "trade block" digest, gamified pitch suggestions? Worth a product riff with Rob.
- Does this become the product's center of gravity (in-season co-manager) with draft as the on-ramp? Likely yes — worth naming explicitly.
