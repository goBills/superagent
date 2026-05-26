"""Deterministic guardrail against unsupported narrative in agent answers.

Prompt rules alone did not reliably stop the agent from editorializing beyond the
tool data (e.g. "Hall of Fame caliber", "prime development window", "team upgrade
could boost his opportunities", "third-year breakout potential", "uncertain QB
play", "injury-shortened season"). This module detects those high-confidence
narrative/hype/speculation markers so run_agent can force a fact-only rewrite, and
so the behavior is unit-testable rather than hoped-for.

These patterns target claims that a Superagent tool never returns as a fact:
career-arc language, team/situation speculation, injury-cause inference, and pure
hype superlatives. Plain data reads (current team, age, years_exp, injury_status,
market rank/value, production trend, bye, roster fit) do not match them.
"""

from __future__ import annotations

import re

_NARRATIVE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # Hype superlatives
    ("hall of fame", re.compile(r"hall of fame", re.IGNORECASE)),
    ("elite", re.compile(r"\belite\b", re.IGNORECASE)),
    ("must-grab", re.compile(r"must[-\s]grab", re.IGNORECASE)),
    ("cant pass up", re.compile(r"can(?:'|’)?t (?:pass up|miss)", re.IGNORECASE)),
    # Career-arc language
    ("breakout", re.compile(r"breakout", re.IGNORECASE)),
    ("development window", re.compile(r"development window", re.IGNORECASE)),
    ("prime window/phase", re.compile(r"prime (?:development|window|year|time|target|breakout|phase)", re.IGNORECASE)),
    ("in his prime", re.compile(r"(?:in|entering|approaching|reaching|past)\s+(?:his|their|her)\s+prime", re.IGNORECASE)),
    ("leap", re.compile(r"\bleap\b", re.IGNORECASE)),
    # Team / situation speculation
    ("team upgrade", re.compile(r"team upgrade", re.IGNORECASE)),
    ("could boost", re.compile(r"could boost", re.IGNORECASE)),
    ("upgrade boosts opportunity", re.compile(r"upgrad\w*\b.{0,30}(?:boost|opportunit|production|target|offense)", re.IGNORECASE)),
    ("better situation/offense", re.compile(r"better (?:offense|situation|landing|opportunit)", re.IGNORECASE)),
    ("landing spot", re.compile(r"landing spot", re.IGNORECASE)),
    ("qb situation/play", re.compile(r"(?:qb|quarterback)\s+(?:situation|play|uncertaint|concern|carousel)", re.IGNORECASE)),
    ("uncertain qb", re.compile(r"uncertain\w*\b.{0,20}(?:qb|quarterback)", re.IGNORECASE)),
    # Injury-cause inference (only injury_status from a tool is allowed)
    ("injury-shortened", re.compile(r"injury[-\s]shortened", re.IGNORECASE)),
    ("injury-plagued", re.compile(r"injury[-\s]plagued", re.IGNORECASE)),
    ("battled injuries", re.compile(r"battl\w*\s+injur", re.IGNORECASE)),
    ("banged up", re.compile(r"banged up", re.IGNORECASE)),
]


def detect_unsupported_narrative(text: str) -> list[str]:
    """Return the matched narrative/hype snippets found in ``text`` (empty if clean)."""
    if not text:
        return []
    hits: list[str] = []
    seen: set[str] = set()
    for _label, pattern in _NARRATIVE_PATTERNS:
        match = pattern.search(text)
        if match:
            snippet = match.group(0).strip().lower()
            if snippet not in seen:
                seen.add(snippet)
                hits.append(match.group(0).strip())
    return hits
