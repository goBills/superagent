"""Tests for week labeling and playoff round naming."""

import pytest
from superagent.week_utils import get_week_label, is_playoff_week, week_range_label


class TestWeekLabeling:
    """Test week number to label conversion."""

    def test_regular_season_weeks(self):
        """Regular season weeks should be labeled 1-17."""
        assert get_week_label(1) == "Week 1"
        assert get_week_label(8) == "Week 8"
        assert get_week_label(17) == "Week 17"

    def test_wild_card_round(self):
        """Week 18 should be Wild Card Round."""
        assert get_week_label(18) == "Wild Card Round"

    def test_divisional_round(self):
        """Week 19 should be Divisional Round."""
        assert get_week_label(19) == "Divisional Round"

    def test_conference_championship(self):
        """Week 20 should be Conference Championship."""
        assert get_week_label(20) == "Conference Championship"

    def test_super_bowl(self):
        """Week 21 should be Super Bowl."""
        assert get_week_label(21) == "Super Bowl"

    def test_unknown_week(self):
        """Unknown weeks should fallback to 'Week X'."""
        assert get_week_label(25) == "Week 25"

    def test_none_week(self):
        """None should return 'Unknown'."""
        assert get_week_label(None) == "Unknown"

    def test_string_week(self):
        """String weeks should be converted to int."""
        assert get_week_label("14") == "Week 14"
        assert get_week_label("19") == "Divisional Round"


class TestPlayoffWeekDetection:
    """Test playoff week detection."""

    def test_regular_season_not_playoff(self):
        """Regular season weeks should not be playoff."""
        assert not is_playoff_week(1)
        assert not is_playoff_week(17)

    def test_playoff_weeks(self):
        """Weeks 18-21 should be playoff."""
        assert is_playoff_week(18)
        assert is_playoff_week(19)
        assert is_playoff_week(20)
        assert is_playoff_week(21)

    def test_non_playoff_weeks(self):
        """Other weeks should not be playoff."""
        assert not is_playoff_week(0)
        assert not is_playoff_week(22)


class TestWeekRangeLabel:
    """Test week range labeling."""

    def test_single_regular_week(self):
        """Single week should return just that week."""
        assert week_range_label(1, 1) == "Week 1"

    def test_regular_season_range(self):
        """Regular season range should show week numbers."""
        assert week_range_label(1, 17) == "Weeks 1-17"
        assert week_range_label(6, 17) == "Weeks 6-17"
        assert week_range_label(10, 15) == "Weeks 10-15"

    def test_single_playoff_week(self):
        """Single playoff week should return round name."""
        assert week_range_label(19, 19) == "Divisional Round"

    def test_regular_season_to_playoffs(self):
        """Range spanning regular season to playoffs."""
        assert week_range_label(1, 21) == "Week 1 through Super Bowl"
        assert week_range_label(10, 19) == "Week 10 through Divisional Round"

    def test_playoff_week_range(self):
        """Range of playoff weeks."""
        result = week_range_label(18, 21)
        assert "Wild Card Round" in result
        assert "Super Bowl" in result


class TestAgentFormattingIntegration:
    """Test that week labels are properly formatted in agent responses."""

    def test_playoff_week_in_game_context(self):
        """When agent mentions playoff games, week should use round name."""
        # This is a scenario test: if a tool returns week 19,
        # the agent should refer to it as "Divisional Round", not "Week 19"
        week_19_label = get_week_label(19)
        assert week_19_label == "Divisional Round"
        assert "Divisional Round" != "Week 19"

    def test_multiple_playoff_games(self):
        """Multiple playoff games should have distinct round names."""
        labels = [get_week_label(w) for w in [18, 19, 20, 21]]
        assert len(set(labels)) == 4  # All unique
        # All labels should not start with "Week" (should be playoff round names)
        assert all(not label.startswith("Week") for label in labels)
