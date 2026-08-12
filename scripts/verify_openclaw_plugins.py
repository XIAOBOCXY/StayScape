"""Verify the runtime plugins required by StayScape are discoverable.

The OpenClaw CLI owns plugin discovery; this small checker only validates its
JSON output and never trusts a directory existing on disk as proof of readiness.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any


REQUIRED = {"qwen", "stayscape-openclaw-plugin"}


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
        print(f"OpenClaw plugin discovery returned invalid JSON: {exc}", file=sys.stderr)
        return 2
    found = {name for name in REQUIRED | {"feishu"} if name in set(strings(payload))}
    missing = REQUIRED - found
    feishu_enabled = os.environ.get("FEISHU_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    if feishu_enabled and "feishu" not in found:
        missing.add("feishu")
    print(f"OpenClaw plugins found: {', '.join(sorted(found)) or 'none'}")
    if missing:
        print(f"Missing required runtime plugins: {', '.join(sorted(missing))}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
