# News Moat — the Agent Farm (design spec, v0)

**Status:** Design-first. Nothing built. This is the contract to react to (Rob + Claude + Codex) before we write code — same protocol as the Trade Mode gates.
**Authors:** Claude (this draft), for Rob + Codex review.
**Date:** 2026-05-30.

---

## 0. The thesis (why this is the moat)

Salam, validating the trade beta: *"this is what fantasy needs so bad."* Then his asks circled one thing — **context the incumbents don't give**: beat-writer signal, official injury notes with an estimated return, suspension flags. Rob's framing: *"There's no context in the offseason — just news,"* and *"build something that polls sources like beat writers and official injury sources and having an agent farm instead of using APIs… each team has a collection of agents… my own data."*

The wedge: **Yahoo/ESPN/Sleeper repackage the same fluff player blurbs.** A proprietary, continuously-refreshed, *attributed, signal-not-fluff* news+injury layer — built by orchestrated agents over data **we own** — is:
1. The honest version of *"always two weeks ahead"* (real events drive it, nothing faked).
2. The answer to **dead post-draft / offseason engagement** (when there are no stats, there's news).
3. The fuel for **Trade Mode** (injury context, buy-low/sell-high, "his stock is moving").
4. Directly Salam's asks: **hover injury notes + estimated return + suspension flags.**

This is the biggest swing on the roadmap. It earns a real spec.

---

## 1. What it produces — the data product

One owned record per signal, keyed to our canonical player: **`player_news_signal`**.

```
player_news_signal {
  canonical_player_id        # our identity (resolver maps prose mentions → this)
  signal_type                # injury | suspension | role_change | depth_chart |
                             #   holdout | transaction | return | other
  status                     # e.g. "Questionable", "IR", "Suspended 4 games",
                             #   "Starter", "Released" — verbatim category, not invented
  est_return                 # ONLY if a source stated one: "Week 8" / "training camp" / null
  headline                   # one-line signal-not-fluff summary (no hype, no projection)
  confidence                 # high | medium | unconfirmed  (driven by §3 trust + corroboration)
  direction                  # up | down | flat  (honest stock read — derived from real events)
  sources[] {                # PROVENANCE IS MANDATORY — every fact links back
    outlet, author, url, published_at, source_tier (1-4), excerpt
  }
  corroboration_count        # # of independent qualifying sources
  first_seen, last_updated
}
```

Non-negotiables baked into the shape:
- **No fact without a source.** `sources[]` is required; a signal with zero qualifying sources is not written.
- **No invented dates/severity.** `est_return` is null unless a source literally stated one — the model extracts, it does not predict.
- **Confidence is explicit**, never hidden — `unconfirmed` is a first-class, surfaceable state ("report, not confirmed").

---

## 2. Architecture — the agent farm (4 tiers + orchestrator)

Rob's instinct ("each team has a collection of agents") maps cleanly to a fan-out/fan-in pipeline. The `Workflow` primitive is exactly this shape (collectors → aggregators → synthesis → editor → write).

```
ORCHESTRATOR (scheduler + fan-out + write)
  │
  ├─ TEAM AGENT × 32  (one per NFL team — "the collection of agents per team")
  │     owns: that team's roster + its source list (beat writers, official injury report, team site)
  │     │
  │     ├─ SOURCE COLLECTOR × N   (cheap model — Haiku)
  │     │     fetch one source (RSS item / official report / page), extract candidate facts
  │     │     I/O + extraction only; no judgment
  │     │
  │     └─ PLAYER SYNTHESIS        (merge a team's collector output per player:
  │           dedup, resolve conflicts by recency × source tier, draft the signal)
  │
  └─ EDITOR / CREDIBILITY GATE  (the adversarial pass — §3)
        corroboration check, trust-tier gate, "signal not fluff" rewrite,
        kill or label-as-unconfirmed → only survivors get written
```

- **Collectors are dumb and cheap** (Haiku): fetch + extract stated facts with provenance. Volume tier.
- **Synthesis is per-team** (Sonnet): one team's facts merged into per-player drafts.
- **Editor is the expensive, careful pass** (Opus): the credibility bar. This is where "better zero than a dumb deal" becomes **"better no signal than a fabricated injury."**
- **Orchestrator** schedules (§6 cadence), fans out, writes survivors to the store.

Phase-0 can be a literal `Workflow` over **one** team and 2–3 sources to prove quality + cost before any infra.

---

## 3. The credibility bar (this is the whole game)

We earned trust on trades by refusing bad deals. News is higher-stakes — a wrong "out for the season" tanks a user's trade. **Source trust hierarchy:**

| Tier | Source | Use |
|---|---|---|
| **1** | Official: NFL injury report, team site, official transactions | Can state as fact alone |
| **2** | Established **named** beat writers (team-specific, verified) | Can state as fact with 1 corroboration, or alone for soft signals |
| **3** | National insiders / reputable aggregators | Needs a Tier-1/2 corroboration to be `high` confidence |
| **4** | Anonymous / unverified social / rumor | Never stated as fact — `unconfirmed` at most, or dropped |

**Hard rules (mirror the trade gates):**
1. **Status changes** (injury/suspension) require **Tier-1 OR (Tier-2 + corroboration)** to be `high`. Else `medium`/`unconfirmed`.
2. **No fabrication.** `est_return`, severity, and dates are *extracted-only*. If no source said it, it's null. The editor's explicit job is to delete invented specifics.
3. **Corroboration raises confidence; it never invents the fact.** One source = the fact exists at that source's tier; more independent sources = higher confidence.
4. **Unconfirmed is labeled, not hidden.** We surface "Report (unconfirmed): …" — honest, and still useful. We do **not** silently upgrade it.
5. **Recency × tier conflict resolution.** Newer Tier-1 beats older Tier-2. Same tier → newest wins, but keep both in `sources[]`.

`direction` (stock up/down/flat) is **derived from the real event**, not a vibe: a confirmed injury → down; a confirmed return/role bump → up; ambiguous → flat. It's honest because it's event-anchored, and it's what powers buy-low/sell-high in Trade Mode.

---

## 4. Provenance & honesty = the brand

Every surfaced line carries **who + when + link**: *"Est. return: Week 8 — per [Beat Writer], May 28 ([link])."* Never a bare "Week 8." This is simultaneously (a) the visible differentiator vs incumbent fluff, (b) our legal/ethical posture (attribution, summarize-and-link, no republishing), and (c) what lets a user *trust* a trade nudge. It's the same honesty line we drew on projections: **show the source, never fake the certainty.**

---

## 5. Legal / ToS reality — the honest part Rob has to decide

Rob's "agent farm **instead of APIs**" is right on the *value/cost* axis (own the data, don't pay per-call) but I have to be straight about the **legal/ToS** axis, the same way we parked FantasyPros for commercial-licensing reasons:

- **X / Twitter is the landmine.** "X integration grabbing beat writers" via scraping is (a) against X ToS, (b) technically hostile — they killed the free API and aggressively block scrapers, so it's *fragile* infra that can vanish overnight, and (c) legally gray for a product Rob intends to **sell**. **Recommendation: do NOT build the moat's foundation on X scraping.** Treat social as a Phase-3, gated path — only via the **official X API (paid)** or a **licensed provider**, and only if the economics clear. Building the core on something that can be shut off or invite a C&D is the wrong base for a commercial venture.
- **Beat writers / outlets:** respect `robots.txt`; prefer **RSS feeds** and official feeds; **summarize + attribute + link**, never republish full text. Most beat writers publish through outlet/team RSS we can consume cleanly.
- **Official sources are the safe, high-trust base:** NFL official injury reports, team sites, official transaction wires. **Start here** — highest trust (Tier 1) *and* lowest legal risk. The moat's spine should be official + RSS beat writers; social is a maybe-later garnish, not the foundation.

**My honest read: the legally-clean, high-trust sources (official injury reports + outlet/beat RSS) are enough to deliver Salam's asks and the offseason-context wedge. We don't need X to win — and betting on X scraping would be betting the product on a foundation someone else controls.**

---

## 6. Cost & cadence (an agent farm isn't free)

32 teams × N sources × continuous = real tokens. Controls:
- **Cheap collectors (Haiku), expensive editor (Opus) only on survivors.** Most volume runs cheap.
- **Cadence scales to season phase + engagement:** offseason = daily; in-season = multiple/day + gameday spikes; event-triggered refresh on official-report drops.
- **Cache + diff:** only re-process changed source items; a signal unchanged since `last_updated` isn't re-edited.
- **Scale the fleet to budget**, not "all 32 always": prioritize teams with rostered players across active leagues.

---

## 7. Storage + integration surfaces

- **Store:** new `player_news_signal` table (Postgres product DB), keyed on `canonical_player_id`, with the §1 shape. Codex's lane (model + migration + crosswalk).
- **Surfaces (Claude's lane):**
  - **Trade cards:** injury/suspension chip (next to the bye chip we just shipped) + `direction` for buy-low/sell-high framing.
  - **Hover injury notes + est. return + suspension flag** — Salam's direct ask — on cards, My Team rail, board.
  - **Offseason "what changed" feed** — the engagement surface when there are no stats.
- **Reuse:** the bye-chip pattern (v0.18.2) is the template for an attributed, honest, provenance-carrying chip.

---

## 8. Phasing

- **Phase 0 — Spike (cheap, no infra).** A `Workflow` over **one** team, **2–3 clean sources** (official injury report + 1 beat-writer RSS + team site). Collect → synthesize → editor-gate → output structured JSON with provenance. **Goal: prove signal-not-fluff quality + measure cost.** No persistence, no UI. Decision gate before anything else.
- **Phase 1 — Persistence + hover.** Codex builds the table + scheduled refresh for all 32 from official+RSS; Claude surfaces injury/suspension chips + hover notes (with provenance + est. return) on Trade cards / My Team. **Delivers Salam's asks directly.**
- **Phase 2 — Stock direction + offseason feed.** Event-anchored `direction` → buy-low/sell-high trade angles ("two weeks ahead"); the offseason news feed.
- **Phase 3 — Social (gated).** X/social **only** via official API or licensed provider, only if §5 + §6 economics clear.

---

## 9. Division of labor

- **Claude (tool-logic + UI):** the agent-farm orchestration (Workflow/agent logic), source-extraction prompts, the **editor/credibility gate** + trust-tier rules, name→canonical resolution tuning for prose, and all UI surfaces (chips/hovers/feed).
- **Codex (backend/data):** `player_news_signal` model + migration, the scheduler/refresh job, source-fetch infra (RSS/HTTP fetchers, `robots.txt` compliance, caching/diff), and the prose-mention → `canonical_player_id` crosswalk hardening.
- **Rob (product/owner):** the **source list** (which beat writers/outlets per team), the **X/social legal call** (§5), trust-tier judgment calls, and priority/budget.

---

## 10. Open decisions for Rob (blocking the build, not the spec)

1. **Social posture (§5):** agree to **defer X/social to Phase-3-gated (official-API-or-licensed only)** and build the spine on official + RSS? (My strong recommendation: yes.)
2. **Phase-0 spike:** greenlight a one-team, 2–3-source `Workflow` spike to prove quality + cost before infra? (Cheap, reversible, no persistence.)
3. **Source seed list:** can you (Rob) hand us a starter list of trusted beat writers/outlets per team, or should we propose one for you to edit?

## 11. Risks

- **Fabrication** (LLM invents return dates/severity) → mitigated by extract-only + editor-delete rule (§3.2). Highest-stakes risk.
- **Name resolution in prose** ("Hollywood", "MHJ", nicknames) is messier than draft-board names → crosswalk hardening (Codex) + confidence penalty on ambiguous matches.
- **Source fragility/legal** (esp. social) → §5 posture; build on official + RSS.
- **Cost creep** → §6 cadence + cheap-collector/expensive-editor split + budget-scaled fleet.
- **Staleness reads as wrong** → `last_updated` surfaced on every signal; never present old news as current.
