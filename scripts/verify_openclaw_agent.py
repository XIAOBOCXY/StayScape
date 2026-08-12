"""Verify that the Gateway exposes the one StayScape Agent we route to."""

from __future__ import annotations

import json
import sys
from typing import Any


REQUIRED_AGENT = "stayscape-main"


def agent_ids(value: Any):
    if isinstance(value, dict):
        for key in ("id", "agentId", "agent_id"):
            item = value.get(key)
            if isinstance(item, str):
                yield item
        entries = value.get("entries")
        if isinstance(entries, dict):
            for key in entries:
                if isinstance(key, str):
                    yield key
        for item in value.values():
            yield from agent_ids(item)
    elif isinstance(value, list):
        for item in value:
            yield from agent_ids(item)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(f"OpenClaw agent discovery returned invalid JSON: {exc}", file=sys.stderr)
        return 2
    found = set(agent_ids(payload))
    print(f"OpenClaw agents found: {', '.join(sorted(found)) or 'none'}")
    if REQUIRED_AGENT not in found:
        print(f"Missing required OpenClaw Agent: {REQUIRED_AGENT}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
