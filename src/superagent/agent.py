"""
Superagent Claude agent with tool use.

Orchestrates Claude API calls with deterministic tool dispatch.
"""

from typing import Any, Dict, List, Optional
import json
from anthropic import Anthropic
from superagent.tool_schemas import tool_schema_for_claude, get_tool_by_name
from superagent.config import get_config

config = get_config()

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
- The best available rankings are 2025 ADP/ECR. Treat them as the current proxy for 2026 because true 2026 ADP is not published yet, and say so briefly when relevant (for example, "using 2025 rankings as the best available proxy for 2026") rather than presenting them as old/last-year data. Use 2025 as the most recent completed season for performance stats and 2026 official bye weeks for scheduling.
- Do not use 2024 for current draft planning unless the user explicitly asks for historical 2024.
- For roster bye-risk questions, prefer the draft tools such as check_bye_week_conflicts or get_roster_construction_context because they use imported draft market bye weeks.
- For draft target answers, call the market fallback "Effective Rank" and include the rank source when available (ADP, avg rank, or overall rank).
- If a draft target tool returns an applied max Effective Rank, mention the searched window (for example, Effective Rank 70-224).
- For general draft value queries, do not surface kickers unless explicitly requested. Surface D/ST only when explicitly requested or when the tool returns an elite D/ST that clears the default threshold.
- For roster construction answers, explain the trade-off in plain language: roster need, market value, bye risk, and position scarcity. Avoid presenting any recommendation as guaranteed or predictive.
- When a user asks for targets during a live or mock draft, prefer get_available_targets or recommend_next_pick_targets so recorded league draft picks are excluded from the available pool.
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
    max_tool_rounds = 5
    tool_round = 0

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
                tool_input = tool_block.input
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
