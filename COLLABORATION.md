# Superagent Development: Claude + Codex Collaboration Model

**Status:** Active  
**Last Updated:** 2026-05-25  
**Next Phase:** Phase 10A (Canonical Player Identity)

---

## Current Workflow

This document defines how Claude and Codex collaborate on Superagent development.

### Division of Labor

| Phase/Task | Owner | Context |
|-----------|-------|---------|
| Phase 9A.2 (Admin Questions) | Codex | Implemented, tested (v0.2.6), ready to deploy |
| Bug Fixes (Blocking) | Claude | CORS login bug, Week 19 playoff week bug |
| Phase 10A Planning | Codex + Claude | Design canonical identity layer together |
| Phase 10A Implementation | Codex | After sign-off from Claude |
| Quality Review | Claude | After Codex implementation |

### How We Work Together

**1. Strategic Decisions (Joint)**
- Scope definition (what problem are we solving?)
- Architecture review (is this the right approach?)
- Risk assessment (what can break?)
- **Format:** Async review + feedback loop before implementation

**2. Implementation (Codex-Led)**
- Codex writes code, tests, commits
- Codex documents what changed
- **Format:** Codex notifies Claude when done with checkpoint summary

**3. Quality Review (Claude-Led)**
- Claude verifies tests pass
- Claude checks edge cases
- Claude confirms production readiness
- **Format:** Claude reports findings, confirms ready for deploy

**4. Bug Fixes (Claude-Led)**
- Claude identifies blocking issues
- Claude implements fix + tests
- Claude commits with explanation
- **Format:** Claude notifies team when merged

---

## Recent Bugs Fixed (May 25, 2026)

### Bug #1: Week 19 Playoff Week (BLOCKING)

**Severity:** High (affects all playoff queries)

**Symptom:**
- Users ask about playoff games
- Response shows "Week 19" instead of "Divisional Round"
- Confuses users who know NFL has 17 regular season weeks

**Root Cause:**
- nflverse data labels playoffs as weeks 18-21
- Tools return raw week numbers without translation
- Claude formats them as-is without context

**Status:** **IDENTIFIED, FIX PENDING**
- Claude designed solution (see below)
- Codex will implement in next sprint

**Fix Required:**
```python
# Add to database.py
def get_playoff_round_name(week):
    """Translate week number to playoff round."""
    mapping = {
        18: "Wild Card Round",
        19: "Divisional Round",
        20: "Conference Championship",
        21: "Super Bowl"
    }
    return mapping.get(week, f"Week {week}")
```

Then update all tools to use `get_playoff_round_name()` when returning week info.

**Tests Needed:**
- Week 19 → "Divisional Round"
- Week 20 → "Conference Championship"
- Regular weeks 1-17 stay as-is
- Verify response formatting uses round names, not week numbers

---

### Bug #2: Login Not Persisting (FIXED)

**Severity:** Critical (blocks all user access)

**Symptom:**
- Users create account, log in
- Refresh page → forced to create account again
- Token never saved to localStorage

**Root Cause:**
- CORS misconfiguration on Render deployment
- Frontend origin (`https://superagent-ph31.onrender.com`) was blocked
- Auth requests failed silently
- Token never returned, so never stored

**Status:** **FIXED & COMMITTED**
- Commit: `6402526`
- Changes: dynamic CORS origin list based on `RENDER_EXTERNAL_URL`
- All 169 tests pass

**What Changed:**
- `src/superagent/config.py`: Added `RENDER_EXTERNAL_URL` config
- `src/superagent/api.py`: Refactored CORS to use `get_allowed_origins()`
- In production, automatically allows Render deployment URL

**Next Step:**
- Push to Render
- Test login persistence on live deployment
- Verify localStorage retains token across page reloads

---

## Product Direction (Clarified May 25)

**From:** "NFL research assistant"  
**To:** "Fantasy football decision-support tool"

**Why:** Draft day and waiver wire management are the core use cases. Research is the foundation, but the goal is actionable decisions.

**Consequence:** Phase 10 (Canonical Identity → Draft Tools) is now the critical path.

**Phases 10A-10D:**
- **10A:** Canonical player identity (person-level, never changes)
- **10B:** Draft market ingestion (ADP, rankings, projections)
- **10C:** League settings (PPR, superflex, scoring)
- **10D:** Draft decision tools ("Who's the best value at pick 45 in my league?")

---

## Communication Protocol

### When Claude Finds a Bug
1. **Identify & prioritize** (blocking? high? low?)
2. **Notify Codex** with: symptom, root cause, proposed fix
3. **Implement & test** if blocking
4. **Commit with explanation** so Codex can verify

### When Codex Completes Work
1. **Notify Claude** with: what was built, tests passed, commit hash
2. **Tag version** (v0.2.7, v0.3.0, etc.)
3. **Wait for Claude review** before considering ready to deploy
4. **Deploy after sign-off**

### When Disagreement Arises
1. **State the issue clearly** (not "this is wrong" but "because X, Y risk")
2. **Propose alternative** if critiquing
3. **Accept the smarter take** — whoever has the better argument wins, not ego
4. **Document decision** in commit or COLLABORATION.md for future reference

---

## Definition of Done (for each phase)

✅ **Code is written** (or fixed)  
✅ **Tests pass** (full suite, not just new tests)  
✅ **Commit is clean** (message explains why, not just what)  
✅ **No security holes** (auth, data validation, rate limits respected)  
✅ **Quality review approved** (by peer, not self)  
✅ **Documentation updated** (README, API docs, deployment guide)  
✅ **Version tagged** (v0.2.6, v0.3.0, etc.)  
✅ **Ready to deploy**

---

## Next Immediate Actions

**Today (May 25):**
- [ ] Claude pushes CORS fix to Render + tests login persistence
- [ ] Codex and Claude scope Week 19 playoff week fix

**This Week:**
- [ ] Deploy fixed login (v0.2.7)
- [ ] Implement Week 19 fix (v0.2.8)
- [ ] Run admin dashboard on live Render for 2-3 days
- [ ] Collect user questions via `/admin/questions` for patterns

**Next Week:**
- [ ] Begin Phase 10A (Canonical Player Identity)
- [ ] Decide on first draft data source (DraftSheets template, Sleeper API, etc.)
- [ ] Design league settings schema

---

## Key Files & Branches

- **Main repo:** `/Users/robertcapozzi/Documents/Football AI Project`
- **Active branch:** `main`
- **Latest tag:** `v0.2.6` (Phase 9A.2 admin questions)
- **Next tag:** `v0.2.7` (CORS fix)
- **Config:** `.env`, `src/superagent/config.py`
- **Tests:** `tests/` (169 passing)

---

## Principles We Follow

1. **Build deterministic tools first**
   - The AI is only as good as the data underneath
   - Never ship fuzzy matching without verification

2. **Ship small, iterate fast**
   - v0.2.6, v0.2.7, v0.2.8 are all incremental
   - Don't hold fixes in branches; merge early

3. **Artisan quality**
   - Production code from day one
   - Don't skip error handling for convenience
   - Every commit should be shippable

4. **Transparent about limitations**
   - Tell users what we don't have (injuries, live data, predictions)
   - Let data speak; don't hallucinate

5. **Verify against reality**
   - Cross-check stats vs ESPN/NFL.com
   - Test with real data, not mocks
   - If it breaks in production, we own it

---

## Questions or Changes?

Update this file and commit to main. Keep it in sync with reality.
