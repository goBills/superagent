"""
Superagent Claude agent with tool use.

Orchestrates Claude API calls with deterministic tool dispatch.
"""

from typing import Any, Dict, List, Optional
import json
from anthropic import Anthropic
from superagent.tool_schemas import tool_schema_for_claude, get_tool_by_name
from superagent.config import get_config
from superagent.answer_guard import detect_unsupported_narrative

config = get_config()

DRAFT_MARKET_TOOL_NAMES = {
    "find_draft_targets",
    "get_available_targets",
    "get_draft_sheet",
    "get_draft_context",
    "get_position_needs",
    "get_roster_construction_context",
    "recommend_next_pick_targets",
    "compare_draft_options",
    "get_bye_week_analysis",
    "check_bye_week_conflicts",
}

SYSTEM_PROMPT = """You are Superagent, an NFL research assistant. Your role is to answer natural language questions about NFL statistics, team performance, and player stats using the available tools.

Rules:
- Use tools for all statistical claims. Do not guess or invent statistics.
- If a tool returns an error or cannot find data, acknowledge it clearly.
- If the tools do not provide the answer, say what data is missing.
- Do not provide betting picks or gambling recommendations.
- Be concise and factual. Focus on answering the question, not explaining the tools.
- For 2025 data, note that player stats are derived from play-by-play data.
- The current calendar/NFL season is 2026. Historical player/stat data currently supports NFL seasons 2020-2025, while official 2026 bye-week data is available for draft planning. If a draft-room, draft-value, roster-construction, or bye-risk question implies current/2026, use 2026 bye weeks when the tool provides them and distinguish them from the imported draft market season. Do not call 2025 the current season.
- Fantasy and draft questions are about preparing for the UPCOMING 2026 NFL season. Frame answers as 2026 draft prep (for example, "for your 2026 draft" or "heading into 2026"), not as a recap of last year. Anchor the user to 2026 so the guidance does not feel dated.
- Use the imported draft market season/source returned by the tools for draft ranks. Do not hardcode a rankings year: if tools return 2026 Sleeper ADP, treat that as the current 2026 rank source; if tools return 2025 DraftSheets, describe it as a 2025 proxy. Use 2025 as the most recent completed season for performance stats and 2026 official bye weeks for scheduling.
- For draft-market tools, do NOT pass a season or source for live/current draft questions. Omit them so the tool uses the current imported board season/source and the same season as recorded draft picks. Never pass season=2025 for a live/mock draft recommendation.
- Do not use 2024 for current draft planning unless the user explicitly asks for historical 2024.
- For roster bye-risk questions, prefer the draft tools such as check_bye_week_conflicts or get_roster_construction_context because they use imported draft market bye weeks.
- For draft target answers, call the market fallback "Effective Rank" and include the rank source when available (ADP, avg rank, or overall rank).
- If a draft target tool returns an applied max Effective Rank, mention the searched window (for example, Effective Rank 70-224).
- For general draft value queries, do not surface kickers unless explicitly requested. Surface D/ST only when explicitly requested or when the tool returns an elite D/ST that clears the default threshold.
- For roster construction answers, explain the trade-off in plain language: roster need, market value, bye risk, and position scarcity. Avoid presenting any recommendation as guaranteed or predictive.
- When a user asks for targets during a live or mock draft, prefer get_available_targets or recommend_next_pick_targets so recorded league draft picks are excluded from the available pool.
- For "what's falling to me", "best value", or "who should I grab now" questions during a draft, pass current_pick to the targets tools so results are bounded to players relevant to that pick. A high value delta on a player ranked far below the current pick (for example Effective Rank ~200 when the user is in round 3) does NOT mean "grab now" — that player is a late-round value, not someone falling to this pick. Never pitch a player whose Effective Rank is far past the current pick as a must-grab for an early round; judge "falling" relative to where the user is actually picking.

PLAYER ANSWER CONTRACT (read this carefully — it overrides any instinct to write engaging analysis):
When you evaluate, compare, or recommend a player, every sentence must be traceable to a fact a tool returned. Allowed claims, and nothing else:
  1. Current context (provider fields): current_team (authoritative — use it, NOT the market "team"; if current_team_differs note the market sheet listed the old team; if current_team is null say the player is a free agent/unsigned per the provider), age, years_exp/entry_year/rookie_year for career stage, injury_status (null = healthy), context_updated_at for freshness. If current_context_available is false, say current context is unavailable rather than inventing it.
  2. Market signal: Effective Rank (+ rank source), ECR, value delta, adjusted value, and the current pick.
  3. Production: stats from the player tools and their season-over-season trend. If the latest season declined, state the decline plainly as a risk.
  4. Roster fit and bye week.
Then end with a one-or-two-sentence "Data read" that only restates the above.
FORBIDDEN (these are guesses Superagent has NO data for — never write them): career-arc language (breakout, "second/third-year breakout", prime/development window, leap), team or situation speculation (team upgrade, better offense, "could boost his opportunities", QB situation/play, landing spot), hype superlatives (Hall of Fame, elite, must-grab, ceiling, can't-miss), draft pedigree, coaching/scheme changes, trade rumors, and any cause for missing games (do not say "injury-shortened" unless injury_status explicitly returned it). Use years_exp for career stage, never a guess — a player with years_exp 2 is entering year 3, not a "second-year breakout".
Before you finalize a player answer, re-read it and delete any sentence not backed by one of the four allowed categories. No hype.
"""


def _content_block_to_dict(block: Any) -> Dict[str, Any]:
    """Convert an Anthropic content block or test mock into a message-safe dict."""
    block_type = getattr(block, "type", None)
    if block_type == "text":
        return {"type": "text", "text": getattr(block, "text", "")}
    if block_type == "tool_use":
        return {
            "type": "tool_use",
            "id": getattr(block, "id"),
            "name": getattr(block, "name"),
            "input": getattr(block, "input", {}),
        }
    return {"type": str(block_type or "unknown"), "text": str(block)}


def _normalize_tool_input_for_agent(tool_name: str, tool_input: Any) -> Dict[str, Any]:
    """Apply agent-only safety defaults before deterministic tool dispatch."""
    normalized = dict(tool_input or {}) if isinstance(tool_input, dict) else {}
    if tool_name in DRAFT_MARKET_TOOL_NAMES:
        # Live draft chat should follow the imported board that the UI is using.
        # Keeping a model-supplied 2025/source value can make recommendations read
        # a stale market and miss recorded 2026 draft picks.
        normalized.pop("season", None)
        normalized.pop("source", None)
        normalized.pop("bye_week_season", None)
    return normalized


def _prepare_history(history: Optional[List[Dict[str, str]]], limit: int = 12) -> List[Dict[str, str]]:
    """Return a capped, API-safe history that starts with a user turn."""
    if not history:
        return []

    prepared = [
        {"role": item["role"], "content": item["content"]}
        for item in history
        if item.get("role") in {"user", "assistant"} and isinstance(item.get("content"), str)
    ][-limit:]

    while prepared and prepared[0]["role"] != "user":
        prepared.pop(0)

    return prepared


def _narrative_correction(flagged: List[str]) -> str:
    """Build the fact-only rewrite instruction when the answer editorialized."""
    phrases = "; ".join(flagged[:8])
    return (
        "Your previous answer included claims that are NOT supported by any tool data: "
        f"{phrases}. Rewrite the answer now using ONLY facts the tools returned: current "
        "team, age, years_exp, injury_status, context_updated_at, market rank/value/value "
        "delta, production stats and their season-over-season trend, bye week, and roster "
        "fit. Remove ALL career-arc language (breakout, prime/development window, leap), "
        "team or situation speculation (team upgrade, better offense, QB situation/play, "
        "landing spot), hype superlatives (Hall of Fame, must-grab), and any injury cause "
        "(only state injury_status if a tool returned it). State uncertainty plainly. "
        "Output only the rewritten answer."
    )


def run_agent(
    question: str,
    client: Optional[Anthropic] = None,
    model: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None
) -> Dict[str, Any]:
    """
    Run Claude agent with tool use to answer a question.

    Args:
        question: User's natural language question
        client: Optional Anthropic client (for testing/injection). If None, creates new client.
        model: Optional model override. Defaults to config.ANTHROPIC_MODEL.
        history: Optional conversation history. List of dicts with "role" and "content" keys.
                 Example: [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
                 Will be capped at last 12 items (6 turns) to manage token usage.

    Returns:
        {
            "ok": bool,
            "answer": str,  # Claude's final synthesis (if ok=true)
            "tools_used": [
                {
                    "name": str,
                    "input": dict,
                    "result": dict
                },
                ...
            ],
            "raw_response": dict,  # Simplified response metadata
            "error": str  # (if ok=false)
        }
    """
    if not question or not question.strip():
        return {
            "ok": False,
            "answer": None,
            "tools_used": [],
            "raw_response": {},
            "error": "Question cannot be empty"
        }

    # Initialize client if not provided (for real usage)
    if client is None:
        if not config.ANTHROPIC_API_KEY:
            return {
                "ok": False,
                "answer": None,
                "tools_used": [],
                "raw_response": {},
                "error": "ANTHROPIC_API_KEY not set"
            }
        client = Anthropic(api_key=config.ANTHROPIC_API_KEY)

    if model is None:
        model = config.ANTHROPIC_MODEL

    tools_used = []
    max_tool_rounds = 6
    tool_round = 0
    narrative_retry_used = False

    try:
        # Initialize messages with prior conversation history (capped at last 12 items = 6 turns)
        messages = _prepare_history(history)

        # Append the new question
        messages.append({"role": "user", "content": question})

        # Tool use loop
        while tool_round < max_tool_rounds:
            tool_round += 1

            # Call Claude with tools
            response = client.messages.create(
                model=model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=tool_schema_for_claude(),
                messages=messages
            )

            # Check if Claude wants to use a tool
            tool_use_blocks = [
                block for block in response.content
                if block.type == "tool_use"
            ]

            # If no tool use, Claude is done
            if not tool_use_blocks:
                # Extract final text answer
                answer = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        answer += block.text

                # Deterministic guardrail: if the synthesis editorialized beyond the
                # tool data (career-arc/hype/team-situation/injury-cause language),
                # force exactly one fact-only rewrite before returning.
                flagged = detect_unsupported_narrative(answer)
                if flagged and not narrative_retry_used:
                    narrative_retry_used = True
                    messages.append({"role": "assistant", "content": answer})
                    messages.append({"role": "user", "content": _narrative_correction(flagged)})
                    continue

                # Prepare simplified response metadata
                raw_response = {
                    "model": model,
                    "stop_reason": response.stop_reason,
                    "usage": {
                        "input_tokens": response.usage.input_tokens,
                        "output_tokens": response.usage.output_tokens
                    },
                    "tool_rounds": tool_round
                }

                return {
                    "ok": True,
                    "answer": answer.strip(),
                    "tools_used": tools_used,
                    "raw_response": raw_response,
                    "error": None
                }

            # Process tool use blocks
            assistant_message = {
                "role": "assistant",
                "content": [_content_block_to_dict(block) for block in response.content],
            }
            messages.append(assistant_message)

            tool_results_content = []

            for tool_block in tool_use_blocks:
                tool_name = tool_block.name
                tool_input = _normalize_tool_input_for_agent(tool_name, tool_block.input)
                tool_result = None

                try:
                    # Dispatch tool
                    tool_func = get_tool_by_name(tool_name)
                    tool_result = tool_func(**tool_input)

                except KeyError:
                    # Unknown tool
                    tool_result = {
                        "ok": False,
                        "error": f"Unknown tool: {tool_name}"
                    }

                except TypeError as e:
                    # Tool argument mismatch
                    tool_result = {
                        "ok": False,
                        "error": f"Tool argument error: {str(e)}"
                    }

                except Exception as e:
                    # Other tool execution errors
                    tool_result = {
                        "ok": False,
                        "error": f"Tool execution error: {str(e)}"
                    }

                # Track tool use (even if it failed)
                tools_used.append({
                    "name": tool_name,
                    "input": tool_input,
                    "result": tool_result
                })

                # Add result for Claude
                is_error = tool_result.get("ok") is False
                result_block = {
                    "type": "tool_result",
                    "tool_use_id": tool_block.id,
                    "content": json.dumps(tool_result),
                }
                if is_error:
                    result_block["is_error"] = True
                tool_results_content.append(result_block)

            # Send tool results back to Claude
            messages.append({
                "role": "user",
                "content": tool_results_content
            })

        # Max tool rounds exceeded
        return {
            "ok": False,
            "answer": None,
            "tools_used": tools_used,
            "raw_response": {"tool_rounds": tool_round},
            "error": f"Exceeded max tool rounds ({max_tool_rounds})"
        }

    except Exception as e:
        return {
            "ok": False,
            "answer": None,
            "tools_used": tools_used,
            "raw_response": {},
            "error": f"Agent error: {str(e)}"
        }
