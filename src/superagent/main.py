#!/usr/bin/env python3
"""
Superagent CLI — Interactive NFL research assistant.

Interactive loop that accepts natural language questions about NFL stats,
teams, players, and trends. Uses Claude for reasoning + deterministic tools
for accurate data.

Usage:
    python -m superagent.main
    or
    superagent (if installed)
"""

import sys
import os
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from superagent.agent import run_agent
from superagent.cli import (
    print_welcome,
    print_help,
    format_agent_response,
    format_team_summary,
    format_player_summary,
    format_player_comparison,
    format_epa_trend,
)


def main():
    """Run interactive Superagent CLI."""
    # Check for API key
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("❌ Error: ANTHROPIC_API_KEY not set.")
        print("Set it with: export ANTHROPIC_API_KEY=sk-...")
        return 1

    print_welcome()

    # Conversation history: list of {"role": "user"/"assistant", "content": str}
    history = []

    while True:
        try:
            user_input = input("You: ").strip()

            # Handle special commands
            if not user_input:
                continue
            if user_input.lower() == "exit":
                print("Goodbye! 👋\n")
                break
            if user_input.lower() == "help":
                print_help()
                continue

            # Run agent with conversation history
            print("\n🤔 Thinking...\n")
            result = run_agent(user_input, history=history)

            # Display response and update history
            if result["ok"]:
                answer = result.get("answer", "").strip()
                if answer:
                    print("Agent:", answer)

                # Append this turn to history
                history.append({"role": "user", "content": user_input})
                history.append({"role": "assistant", "content": answer})

                # Cap history at 12 items (6 turns)
                history = history[-12:]

                # Show tools used
                tools_used = result.get("tools_used", [])
                if tools_used:
                    print("\n📊 Tools Used:")
                    for tool in tools_used:
                        name = tool.get("name", "unknown")
                        ok = tool.get("result", {}).get("ok", False)
                        status = "✅" if ok else "❌"
                        print(f"  {status} {name}")
                print()
            else:
                print(f"❌ Error: {result.get('error', 'Unknown error')}\n")

        except KeyboardInterrupt:
            print("\n\nGoodbye! 👋\n")
            break
        except Exception as e:
            print(f"❌ Unexpected error: {str(e)}\n")
            continue

    return 0


if __name__ == "__main__":
    sys.exit(main())
