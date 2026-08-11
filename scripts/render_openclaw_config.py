"""Render the secret-bearing OpenClaw config from the checked-in template.

The output is intentionally written under deploy/generated, which is ignored
by Git.  It is mounted only inside the private Docker network.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from string import Template


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "deploy" / "openclaw" / "openclaw.json.template"
OUTPUT = Path(os.environ.get("OPENCLAW_CONFIG_PATH", ROOT / "deploy" / "generated" / "openclaw.json"))


def csv_values(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def main() -> None:
    token = env("OPENCLAW_GATEWAY_TOKEN")
    if not token:
        raise SystemExit("OPENCLAW_GATEWAY_TOKEN is required to render a live OpenClaw config")
    substitutions = {
        "OPENCLAW_GATEWAY_TOKEN": token,
        "STAYSCAPE_AGENT_TOOL_TOKEN": env("STAYSCAPE_AGENT_TOOL_TOKEN"),
        "STAYSCAPE_API_INTERNAL_URL": env("STAYSCAPE_API_INTERNAL_URL", "http://server:8000"),
        "STAYSCAPE_HOTEL_ID": env("STAYSCAPE_HOTEL_ID", "1"),
        "FEISHU_OPERATOR_OPEN_ID": env("FEISHU_OPERATOR_OPEN_ID"),
        "FEISHU_ACTOR_ROLE": env("FEISHU_ACTOR_ROLE", "HOTEL_OPERATOR"),
        "FEISHU_APP_ID": env("FEISHU_APP_ID"),
        "FEISHU_APP_SECRET": env("FEISHU_APP_SECRET"),
    }
    config = json.loads(Template(TEMPLATE.read_text(encoding="utf-8")).substitute(substitutions))
    feishu_enabled = bool(env("FEISHU_APP_ID") and env("FEISHU_APP_SECRET"))
    feishu = config["channels"]["feishu"]
    feishu["enabled"] = feishu_enabled
    feishu["allowFrom"] = csv_values(env("FEISHU_DM_ALLOW_FROM"))
    feishu["groupAllowFrom"] = csv_values(env("FEISHU_GROUP_ALLOW_FROM"))
    feishu["groupSenderAllowFrom"] = csv_values(env("FEISHU_GROUP_SENDER_ALLOW_FROM"))
    feishu["requireMention"] = env("FEISHU_REQUIRE_MENTION", "true").lower() == "true"
    plugin_config = config["plugins"]["entries"]["stayscape-openclaw-plugin"]["config"]
    plugin_config["hotelId"] = int(env("STAYSCAPE_HOTEL_ID", "1"))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        OUTPUT.chmod(0o600)
    except OSError:
        pass
    print(f"Rendered OpenClaw config: {OUTPUT}")
    print(f"Feishu channel: {'enabled' if feishu_enabled else 'disabled (credentials not supplied)'}")
    print("Agent: stayscape-main")
    print("Skills: stayscape-product-generator, stayscape-visitor-matcher")


if __name__ == "__main__":
    main()
