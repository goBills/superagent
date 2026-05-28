"""Read-only SportsDataIO access probe.

This module intentionally does not persist anything. It answers one question:
which SportsDataIO trial feeds can our key access, and what useful fields do
they return for Superagent's fantasy cockpit?
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from superagent.data.sportsdataio_client import (
    TRIAL_PROBE_ENDPOINTS,
    SportsDataIOClient,
    SportsDataIOEndpoint,
    SportsDataIOError,
    sample_records,
)


def probe_sportsdataio_access(season: int = 2026) -> dict[str, Any]:
    """Probe the trial endpoints and return a redacted access summary."""
    client = SportsDataIOClient()
    results = []
    for endpoint in TRIAL_PROBE_ENDPOINTS:
        results.append(_probe_endpoint(client, endpoint, season=season))
    return {
        "ok": True,
        "season": season,
        "endpoints": results,
        "summary": {
            "checked": len(results),
            "accessible": sum(1 for result in results if result["ok"]),
            "blocked_or_failed": sum(1 for result in results if not result["ok"]),
        },
    }


def _probe_endpoint(
    client: SportsDataIOClient,
    endpoint: SportsDataIOEndpoint,
    *,
    season: int,
) -> dict[str, Any]:
    try:
        payload = client.get_json(endpoint.path, season=season)
    except SportsDataIOError as exc:
        return {
            "name": endpoint.name,
            "path": endpoint.path,
            "description": endpoint.description,
            "ok": False,
            "error": str(exc),
        }
    except Exception as exc:  # pragma: no cover - defensive CLI guardrail
        return {
            "name": endpoint.name,
            "path": endpoint.path,
            "description": endpoint.description,
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }

    return {
        "name": endpoint.name,
        "path": endpoint.path,
        "description": endpoint.description,
        "ok": True,
        "payload_type": type(payload).__name__,
        "count": len(payload) if isinstance(payload, list) else (1 if isinstance(payload, dict) else None),
        "sample_keys": _sample_keys(payload),
        "samples": sample_records(payload),
    }


def _sample_keys(payload: Any) -> list[str]:
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return list(payload[0].keys())[:30]
    if isinstance(payload, dict):
        return list(payload.keys())[:30]
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe SportsDataIO trial feed access without persisting data.")
    parser.add_argument("--season", type=int, default=2026)
    args = parser.parse_args()
    print(json.dumps(probe_sportsdataio_access(season=args.season), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
