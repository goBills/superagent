#!/usr/bin/env python3
"""
Manual smoke test for Superagent agent with real Claude API.

Only runs if ANTHROPIC_API_KEY is set.
Usage: python scripts/smoke_agent.py
"""

import sys
import os
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from superagent.agent import run_agent


def main():
    """Run a few test queries against real Claude API."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("⚠️  ANTHROPIC_API_KEY not set. Skipping smoke test.")
        print("   To run: export ANTHROPIC_API_KEY=sk-... && python scripts/smoke_agent.py")
        return 0

    print("🚀 Superagent Smoke Test (Real Claude API)")
    print("=" * 60)

    test_queries = [
        "What's Josh Allen's EPA per play in 2024?",
        "Compare Josh Allen and Lamar Jackson's passing yards in 2024.",
        "How did the Bills offense perform in weeks 1-5 of 2024?",
    ]

    for i, query in enumerate(test_queries, 1):
        print(f"\n[Query {i}] {query}")
        print("-" * 60)

        result = run_agent(query)

        if result["ok"]:
            print(f"✅ Answer: {result['answer']}")
            if result["tools_used"]:
                print(f"📊 Tools used: {', '.join(t['name'] for t in result['tools_used'])}")
        else:
            print(f"❌ Error: {result['error']}")

        print()

    print("=" * 60)
    print("✅ Smoke test complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
