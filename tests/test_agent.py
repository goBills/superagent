"""
Tests for Superagent Claude agent with tool use.

Uses mocked Anthropic client to avoid API calls in CI.
"""

import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from superagent.agent import run_agent
from superagent.tool_schemas import tool_schema_for_claude


class MockMessage:
    """Mock Anthropic API message."""

    def __init__(self, stop_reason="end_turn", usage=None, content=None):
        self.stop_reason = stop_reason
        self.usage = usage or Mock(input_tokens=100, output_tokens=50)
        self.content = content or []


class TestAgentBasic:
    """Test basic agent functionality."""

    def test_empty_question(self):
        """Test agent with empty question."""
        result = run_agent("")
        assert result["ok"] == False
        assert result["error"] is not None

    def test_agent_no_api_key_no_client(self, monkeypatch):
        """Test agent fails gracefully without API key and no client."""
        # Ensure no API key
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        # Monkey-patch config to have empty API key
        from superagent import config as config_module
        original_key = config_module.get_config().ANTHROPIC_API_KEY
        config_module.get_config().ANTHROPIC_API_KEY = ""

        result = run_agent("What's Josh Allen's EPA?")
        assert result["ok"] == False
        assert "API_KEY" in result["error"] or "ANTHROPIC_API_KEY" in result["error"]

        # Restore
        config_module.get_config().ANTHROPIC_API_KEY = original_key

    def test_agent_with_mocked_client_simple_answer(self):
        """Test agent that gets a simple text answer (no tool use)."""
        # Mock Claude response with just text
        mock_client = Mock()
        mock_response = MockMessage(
            content=[Mock(type="text", text="The Buffalo Bills went 13-4 in 2024.")]
        )
        mock_client.messages.create.return_value = mock_response

        result = run_agent("How did the Bills do in 2024?", client=mock_client)

        assert result["ok"] == True
        assert "13-4" in result["answer"]
        assert result["tools_used"] == []
        assert result["raw_response"]["stop_reason"] == "end_turn"
        # Clean answer: no narrative guard regeneration, so exactly one model call.
        assert mock_client.messages.create.call_count == 1

    def test_agent_regenerates_when_answer_editorializes(self):
        """If the synthesis hypes beyond the data, the guard forces one fact-only rewrite."""
        mock_client = Mock()
        hype = MockMessage(
            content=[Mock(type="text", text="He has Hall of Fame caliber, third-year breakout potential.")]
        )
        clean = MockMessage(
            content=[Mock(type="text", text="Current team SF, age 23, years_exp 2. ECR 32, value delta +11.7.")]
        )
        mock_client.messages.create.side_effect = [hype, clean]

        result = run_agent("Tell me about this player for my pick", client=mock_client)

        assert result["ok"] == True
        # The hyped answer was replaced by the clean rewrite.
        assert "Hall of Fame" not in result["answer"]
        assert "breakout" not in result["answer"]
        assert "ECR 32" in result["answer"]
        # Exactly one regeneration (two model calls total).
        assert mock_client.messages.create.call_count == 2

    def test_agent_regenerates_only_once(self):
        """Guard retries at most once; a still-hyped rewrite is returned, not looped forever."""
        mock_client = Mock()
        hype = MockMessage(content=[Mock(type="text", text="Hall of Fame breakout, must-grab.")])
        still_hype = MockMessage(content=[Mock(type="text", text="Still a breakout must-grab pick.")])
        mock_client.messages.create.side_effect = [hype, still_hype]

        result = run_agent("Tell me about this player", client=mock_client)

        assert result["ok"] == True
        # Did not loop infinitely — stopped after one retry.
        assert mock_client.messages.create.call_count == 2

    def test_agent_with_tool_use_single_tool(self):
        """Test agent that calls a single tool and gets answer."""
        mock_client = Mock()

        # First response: Claude asks to use get_team_summary
        tool_use_block = Mock()
        tool_use_block.type = "tool_use"
        tool_use_block.id = "tool_1"
        tool_use_block.name = "get_team_summary"
        tool_use_block.input = {"team": "BUF", "season": 2024}

        first_response = MockMessage(
            stop_reason="tool_use",
            content=[tool_use_block]
        )

        # Second response: Claude's final answer
        second_response = MockMessage(
            stop_reason="end_turn",
            content=[Mock(type="text", text="The Bills had a great 2024 season with a 13-4 record.")]
        )

        mock_client.messages.create.side_effect = [first_response, second_response]

        result = run_agent("What's the Bills record in 2024?", client=mock_client)

        assert result["ok"] == True
        assert "13-4" in result["answer"]
        assert len(result["tools_used"]) == 1
        assert result["tools_used"][0]["name"] == "get_team_summary"
        assert result["tools_used"][0]["input"]["team"] == "BUF"
        assert result["tools_used"][0]["input"]["season"] == 2024

    def test_agent_strips_stale_season_and_source_from_live_draft_tools(self, monkeypatch):
        """A model-supplied 2025 draft season must not force the stale board."""
        mock_client = Mock()
        captured = {}

        tool_use_block = Mock()
        tool_use_block.type = "tool_use"
        tool_use_block.id = "tool_draft"
        tool_use_block.name = "recommend_next_pick_targets"
        tool_use_block.input = {
            "league_id": 1,
            "season": 2025,
            "source": "draftsheetsv6",
            "bye_week_season": 2025,
            "current_pick": 59,
        }

        first_response = MockMessage(stop_reason="tool_use", content=[tool_use_block])
        second_response = MockMessage(
            stop_reason="end_turn",
            content=[Mock(type="text", text="Use the current 2026 board; drafted players are excluded.")],
        )
        mock_client.messages.create.side_effect = [first_response, second_response]

        def fake_get_tool_by_name(name):
            assert name == "recommend_next_pick_targets"

            def fake_tool(**kwargs):
                captured.update(kwargs)
                return {"ok": True, "data": [], "meta": {"market_season": 2026}}

            return fake_tool

        monkeypatch.setattr("superagent.agent.get_tool_by_name", fake_get_tool_by_name)

        result = run_agent("League ID 1. Pick 59. Who do I take next?", client=mock_client)

        assert result["ok"] is True
        assert captured == {"league_id": 1, "current_pick": 59}
        assert result["tools_used"][0]["input"] == {"league_id": 1, "current_pick": 59}

    def test_draft_tool_schemas_tell_agent_to_omit_live_draft_season(self):
        schemas = {schema["name"]: schema for schema in tool_schema_for_claude()}
        draft_season_description = schemas["recommend_next_pick_targets"]["input_schema"]["properties"]["season"][
            "description"
        ]
        stat_season_description = schemas["get_team_summary"]["input_schema"]["properties"]["season"]["description"]

        assert "OMIT" in draft_season_description
        assert "current imported board season" in draft_season_description
        assert "2020-2025" not in draft_season_description
        assert "2020-2025" in stat_season_description

    def test_bench_strategy_questions_get_small_draft_tool_menu(self):
        mock_client = Mock()
        mock_response = MockMessage(content=[Mock(type="text", text="Prioritize RB and WR bench upside.")])
        mock_client.messages.create.return_value = mock_response

        result = run_agent(
            "League ID 1. For draft purposes use the imported draft market data and 2026 bye weeks; "
            "do not ask me which season. My current roster is Josh Allen, James Cook, Travis Kelce. "
            "Draft board: 20 picks recorded: #1 Team->Bijan Robinson. I am at pick 59. "
            "Question: how should I stack my bench?",
            client=mock_client,
        )

        assert result["ok"] is True
        tool_names = {tool["name"] for tool in mock_client.messages.create.call_args.kwargs["tools"]}
        assert tool_names == {
            "get_roster_construction_context",
            "recommend_next_pick_targets",
            "get_available_targets",
            "check_bye_week_conflicts",
        }

    def test_agent_compacts_prior_draft_board_context_from_history(self):
        mock_client = Mock()
        mock_response = MockMessage(content=[Mock(type="text", text="Answer.")])
        mock_client.messages.create.return_value = mock_response
        history = [
            {
                "role": "user",
                "content": (
                    "League ID 1. For draft purposes use the imported draft market data and 2026 bye weeks; "
                    "Draft board: 35 picks recorded: #1 Team->Bijan Robinson; #2 Team->Jahmyr Gibbs. "
                    "I am at pick 36. Question: who should I take next?"
                ),
            },
            {"role": "assistant", "content": "Take the best available RB."},
        ]

        result = run_agent("Question: what about my bench?", client=mock_client, history=history)

        assert result["ok"] is True
        messages = mock_client.messages.create.call_args.kwargs["messages"]
        assert messages[0]["content"] == "Prior draft question: who should I take next?"
        assert "Draft board:" not in messages[0]["content"]

    def test_agent_with_tool_use_multiple_tools(self):
        """Test agent that calls multiple tools."""
        mock_client = Mock()

        # First response: Claude asks to use get_team_summary
        tool_block_1 = Mock()
        tool_block_1.type = "tool_use"
        tool_block_1.id = "tool_1"
        tool_block_1.name = "get_team_summary"
        tool_block_1.input = {"team": "BUF", "season": 2024}

        first_response = MockMessage(
            stop_reason="tool_use",
            content=[tool_block_1]
        )

        # Second response: Claude asks to use get_player_summary
        tool_block_2 = Mock()
        tool_block_2.type = "tool_use"
        tool_block_2.id = "tool_2"
        tool_block_2.name = "get_player_summary"
        tool_block_2.input = {"player_name": "Josh Allen", "season": 2024}

        second_response = MockMessage(
            stop_reason="tool_use",
            content=[tool_block_2]
        )

        # Third response: Claude's final answer
        third_response = MockMessage(
            stop_reason="end_turn",
            content=[Mock(type="text", text="The Bills went 13-4 and Josh Allen had 4367 passing yards.")]
        )

        mock_client.messages.create.side_effect = [first_response, second_response, third_response]

        result = run_agent("How did the Bills do and what were Josh Allen's stats?", client=mock_client)

        assert result["ok"] == True
        assert len(result["tools_used"]) == 2
        assert result["tools_used"][0]["name"] == "get_team_summary"
        assert result["tools_used"][1]["name"] == "get_player_summary"

    def test_agent_with_unknown_tool(self):
        """Test agent handling unknown tool name."""
        mock_client = Mock()

        # Claude asks to use a non-existent tool
        tool_block = Mock()
        tool_block.type = "tool_use"
        tool_block.id = "tool_1"
        tool_block.name = "unknown_tool"
        tool_block.input = {}

        first_response = MockMessage(
            stop_reason="tool_use",
            content=[tool_block]
        )

        # Claude's response after tool error
        second_response = MockMessage(
            stop_reason="end_turn",
            content=[Mock(type="text", text="I encountered an error trying to call that tool.")]
        )

        mock_client.messages.create.side_effect = [first_response, second_response]

        result = run_agent("Hmm?", client=mock_client)

        assert result["ok"] == True
        assert len(result["tools_used"]) == 1
        assert result["tools_used"][0]["name"] == "unknown_tool"
        # Result should show error
        assert result["tools_used"][0]["result"]["ok"] == False

    def test_agent_max_tool_rounds_exceeded(self):
        """Test agent stops after max tool rounds."""
        mock_client = Mock()

        # Keep returning tool_use responses (simulate infinite loop)
        tool_block = Mock()
        tool_block.type = "tool_use"
        tool_block.id = "tool_x"
        tool_block.name = "get_team_summary"
        tool_block.input = {"team": "BUF", "season": 2024}

        response = MockMessage(stop_reason="tool_use", content=[tool_block])

        # Make it return the same response infinitely
        mock_client.messages.create.return_value = response

        result = run_agent("What's the Bills record?", client=mock_client)

        assert result["ok"] == False
        assert "max tool rounds" in result["error"].lower()
        # Cap raised to 6 in v0.6.2 to leave one round for the narrative-guard rewrite.
        assert result["raw_response"]["tool_rounds"] == 6

    def test_agent_output_is_json_safe(self):
        """Test agent output is JSON-serializable."""
        import json

        mock_client = Mock()
        mock_response = MockMessage(
            content=[Mock(type="text", text="The Bills are 13-4.")]
        )
        mock_client.messages.create.return_value = mock_response

        result = run_agent("How are the Bills?", client=mock_client)

        # Should be JSON-serializable
        try:
            json.dumps(result)
        except TypeError as e:
            pytest.fail(f"Agent output is not JSON-serializable: {e}")

    def test_agent_model_override(self):
        """Test agent accepts model parameter."""
        mock_client = Mock()
        mock_response = MockMessage(
            content=[Mock(type="text", text="Answer.")]
        )
        mock_client.messages.create.return_value = mock_response

        result = run_agent(
            "Test?",
            client=mock_client,
            model="claude-3-opus-20250219"
        )

        assert result["ok"] == True
        # Check the model was passed to Claude
        call_args = mock_client.messages.create.call_args
        assert call_args.kwargs["model"] == "claude-3-opus-20250219"

    def test_agent_default_model_comes_from_config(self):
        """Test agent uses configured default model when no override is supplied."""
        mock_client = Mock()
        mock_response = MockMessage(content=[Mock(type="text", text="Answer.")])
        mock_client.messages.create.return_value = mock_response

        result = run_agent("Test?", client=mock_client)

        assert result["ok"] == True
        call_args = mock_client.messages.create.call_args
        assert call_args.kwargs["model"] == "claude-sonnet-4-20250514"


class TestAgentConversationHistory:
    """Test conversation history (Phase 3C)."""

    def test_agent_with_history_single_turn(self):
        """Test agent preserves prior conversation history."""
        mock_client = Mock()
        mock_response = MockMessage(
            content=[Mock(type="text", text="Josh Allen had 4367 passing yards in 2024.")]
        )
        mock_client.messages.create.return_value = mock_response

        # First turn: ask about Josh Allen
        history = []
        result1 = run_agent("Tell me about Josh Allen in 2024", client=mock_client, history=history)

        assert result1["ok"] == True
        assert "4367" in result1["answer"]

        # Verify the first message to Claude was just the question (no prior history)
        call_args = mock_client.messages.create.call_args
        messages = call_args.kwargs["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert "Josh Allen" in messages[0]["content"]

    def test_agent_with_history_two_turns(self):
        """Test agent uses prior context for follow-up questions."""
        mock_client = Mock()

        # First response: answer about Josh Allen
        first_response = MockMessage(
            content=[Mock(type="text", text="Josh Allen had 4367 passing yards in 2024.")]
        )

        # Second response: comparison (should have prior context)
        second_response = MockMessage(
            content=[Mock(type="text", text="Josh Allen: 4367 yards. Lamar Jackson: 4172 yards.")]
        )

        mock_client.messages.create.side_effect = [first_response, second_response]

        # Build history from first turn
        history = [
            {"role": "user", "content": "Tell me about Josh Allen in 2024"},
            {"role": "assistant", "content": "Josh Allen had 4367 passing yards in 2024."}
        ]

        # Second turn: follow-up question
        result = run_agent(
            "Compare him to Lamar Jackson",
            client=mock_client,
            history=history
        )

        assert result["ok"] == True

        # Verify the second message to Claude includes prior context
        call_args = mock_client.messages.create.call_args
        messages = call_args.kwargs["messages"]

        # Should have: prior user turn + prior assistant response + new question
        assert len(messages) == 3
        assert messages[0]["role"] == "user"
        assert "Josh Allen" in messages[0]["content"]
        assert messages[1]["role"] == "assistant"
        assert "4367" in messages[1]["content"]
        assert messages[2]["role"] == "user"
        assert "Lamar Jackson" in messages[2]["content"]

    def test_agent_history_capped_at_12_items(self):
        """Test that history is capped at 12 items (6 turns)."""
        mock_client = Mock()
        mock_response = MockMessage(
            content=[Mock(type="text", text="Answer.")]
        )
        mock_client.messages.create.return_value = mock_response

        # Build a long history (15 items = 7.5 turns)
        history = []
        for i in range(7):
            history.append({"role": "user", "content": f"Question {i}"})
            history.append({"role": "assistant", "content": f"Answer {i}"})
        history.append({"role": "user", "content": "Question 7"})

        result = run_agent("New question", client=mock_client, history=history)

        assert result["ok"] == True

        # Verify the history is capped and starts with a user message for API safety.
        call_args = mock_client.messages.create.call_args
        messages = call_args.kwargs["messages"]

        assert len(messages) <= 13

        assert messages[0]["role"] == "user"

        # And we should have the new question at the end
        assert "New question" in messages[-1]["content"]

    def test_agent_history_drops_leading_assistant_after_cap(self):
        """Test capped odd-length history never starts with assistant."""
        mock_client = Mock()
        mock_response = MockMessage(content=[Mock(type="text", text="Answer.")])
        mock_client.messages.create.return_value = mock_response

        history = [{"role": "assistant", "content": "Dangling assistant answer"}]
        for i in range(6):
            history.append({"role": "user", "content": f"Question {i}"})
            history.append({"role": "assistant", "content": f"Answer {i}"})

        result = run_agent("New question", client=mock_client, history=history)

        assert result["ok"] == True
        messages = mock_client.messages.create.call_args.kwargs["messages"]
        assert messages[0]["role"] == "user"
        assert messages[-1]["content"] == "New question"

    def test_agent_empty_history(self):
        """Test agent works with empty/None history."""
        mock_client = Mock()
        mock_response = MockMessage(
            content=[Mock(type="text", text="Answer.")]
        )
        mock_client.messages.create.return_value = mock_response

        # Test with None
        result = run_agent("Question?", client=mock_client, history=None)
        assert result["ok"] == True

        # Test with empty list
        result = run_agent("Question?", client=mock_client, history=[])
        assert result["ok"] == True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
