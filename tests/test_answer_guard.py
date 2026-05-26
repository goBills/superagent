"""Tests for the deterministic unsupported-narrative guardrail."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from superagent.answer_guard import detect_unsupported_narrative


class TestDetectsRealLeakedPhrases:
    """The exact phrases Codex/Rob flagged from live output must be caught."""

    def test_hall_of_fame(self):
        assert detect_unsupported_narrative("He is a Hall of Fame caliber receiver.")

    def test_team_upgrade_boost(self):
        assert detect_unsupported_narrative("A team upgrade could boost his opportunities.")

    def test_prime_development_window(self):
        assert detect_unsupported_narrative("He is entering his prime development window.")

    def test_third_year_breakout(self):
        assert detect_unsupported_narrative("Strong third-year breakout potential here.")

    def test_uncertain_qb_play(self):
        assert detect_unsupported_narrative("Jacksonville situation has uncertain QB play.")

    def test_injury_shortened(self):
        assert detect_unsupported_narrative("Coming off an injury-shortened season.")

    def test_elite_talent(self):
        assert detect_unsupported_narrative("Getting elite WR talent at pick 31.")

    def test_returns_the_snippets(self):
        hits = detect_unsupported_narrative("Hall of Fame talent with breakout upside.")
        assert any("hall of fame" in h.lower() for h in hits)
        assert any("breakout" in h.lower() for h in hits)


class TestPassesCleanDataReads:
    """Fact-only answers must NOT trip the guard (no false positives)."""

    def test_full_data_read(self):
        clean = (
            "Current team: San Francisco (market sheet listed Tampa Bay). Age 32, "
            "12 years experience, no injury designation per Sleeper (updated 2026-05-26). "
            "Market: ECR 32 vs Effective Rank 39.2, value delta +11.7. Production: 1004 "
            "receiving yards in 2025, down from 1255 in 2024 — a decline and a risk. "
            "Bye week 10, no roster conflict. Data read: solid market value at this cost; "
            "the year-over-year decline and age are the concerns."
        )
        assert detect_unsupported_narrative(clean) == []

    def test_simple_historical_answer(self):
        assert detect_unsupported_narrative("The Buffalo Bills went 13-4 in 2024.") == []

    def test_free_agent_statement(self):
        assert detect_unsupported_narrative(
            "He is currently a free agent per the provider; market lists him at ECR 88."
        ) == []

    def test_empty(self):
        assert detect_unsupported_narrative("") == []
        assert detect_unsupported_narrative(None) == []
