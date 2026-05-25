#!/usr/bin/env python3
"""
Demo script for Superagent MVP capabilities.

Run with:
    python scripts/demo_superagent.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from superagent.agent import run_agent  # noqa: E402


DEMO_QUERIES = [
    "What was Josh Allen's EPA per play in 2024?",
    "Compare Josh Allen and Lamar Jackson in 2024",
    "Get James Cook's weekly usage in 2024",
    "Find late-season RB breakouts in 2024",
    "When are the Bills on bye in 2025?",
    "Show the Bills schedule for 2025",
    "What should I know about Josh Allen's fantasy schedule for 2025?",
    "Compare James Cook and Khalil Shakir fantasy context from Week 10",
]


def main() -> int:
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set.")
        print("Set it in your environment or .env file, then rerun this demo.")
        return 1

    print("\n" + "=" * 60)
    print("Superagent MVP Demo")
    print("=" * 60 + "\n")

    history = []
    for index, query in enumerate(DEMO_QUERIES, 1):
        print(f"\n[Query {index}/{len(DEMO_QUERIES)}]")
        print(f"You: {query}\n")

        result = run_agent(query, history=history)
        if result.get("ok"):
            print(f"Agent: {result.get('answer')}\n")
            history.append({"role": "user", "content": query})
            history.append({"role": "assistant", "content": result.get("answer", "")})
            history = history[-12:]
        else:
            print(f"Error: {result.get('error')}\n")

        tools_used = result.get("tools_used", [])
        if tools_used:
            print("Tools used:")
            for tool in tools_used:
                print(f"  - {tool.get('name')}")

        print("-" * 60)

    print("\nDemo complete.")
    print("Start interactive CLI with: python -m superagent.main")
    print("Or web UI with: python -m superagent.api")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
