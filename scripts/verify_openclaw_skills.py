"""Verify the two StayScape skills in ``openclaw skills list --json`` output."""

from __future__ import annotations

import json
import sys
from typing import Any

REQUIRED = {"stayscape-product-generator", "stayscape-visitor-matcher"}


def strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(f"OpenClaw skill discovery returned invalid JSON: {exc}", file=sys.stderr)
        return 2
    found = {name for name in REQUIRED if name in set(strings(payload))}
    missing = REQUIRED - found
    print(f"OpenClaw skills found: {', '.join(sorted(found)) or 'none'}")
    if missing:
        print(f"Missing required skills: {', '.join(sorted(missing))}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
