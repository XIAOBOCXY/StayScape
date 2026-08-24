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
    primary_model = env("OPENCLAW_PRIMARY_MODEL").strip()
    if not primary_model:
        raise SystemExit("OPENCLAW_PRIMARY_MODEL must be set in .env")
    substitutions = {
        "OPENCLAW_GATEWAY_TOKEN": token,
        "STAYSCAPE_AGENT_TOOL_TOKEN": env("STAYSCAPE_AGENT_TOOL_TOKEN"),
        "STAYSCAPE_API_INTERNAL_URL": env("STAYSCAPE_API_INTERNAL_URL", "http://server:8000"),
        "STAYSCAPE_HOTEL_ID": env("STAYSCAPE_HOTEL_ID", "1"),
        "OPENCLAW_PRIMARY_MODEL": primary_model,
        "OPENCLAW_RUNTIME_PLUGIN_ROOT": env("OPENCLAW_RUNTIME_PLUGIN_ROOT", "/opt/stayscape/runtime-plugins"),
        "FEISHU_APP_ID": env("FEISHU_APP_ID"),
        "FEISHU_APP_SECRET": env("FEISHU_APP_SECRET"),
    }
    config = json.loads(Template(TEMPLATE.read_text(encoding="utf-8")).substitute(substitutions))
    feishu_enabled = (
        env("FEISHU_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
        and bool(env("FEISHU_APP_ID") and env("FEISHU_APP_SECRET"))
    )
    feishu = config["channels"]["feishu"]
    feishu["enabled"] = feishu_enabled
    feishu["allowFrom"] = csv_values(env("FEISHU_DM_ALLOW_FROM"))
    feishu["groupAllowFrom"] = csv_values(env("FEISHU_GROUP_ALLOW_FROM"))
    feishu["groupSenderAllowFrom"] = csv_values(env("FEISHU_GROUP_SENDER_ALLOW_FROM"))
    feishu["requireMention"] = env("FEISHU_REQUIRE_MENTION", "true").lower() in {"1", "true", "yes", "on"}
    config["plugins"]["entries"]["feishu"]["enabled"] = feishu_enabled
    plugin_config = config["plugins"]["entries"]["stayscape-openclaw-plugin"]["config"]
    plugin_config["hotelId"] = int(env("STAYSCAPE_HOTEL_ID", "1"))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        # Docker bind mounts preserve host ownership.  The Gateway runs as the
        # node user (GID 1000), so grant that group read-only access without
        # making the token-bearing rendered config world-readable.
        OUTPUT.chmod(0o640)
        os.chown(OUTPUT, -1, int(env("OPENCLAW_CONFIG_GROUP_ID", "1000")))
    except (OSError, ValueError):
        pass
    print(f"Rendered OpenClaw config: {OUTPUT}")
    print(f"Feishu channel: {'enabled' if feishu_enabled else 'disabled (credentials not supplied)'}")
    print("Agent: stayscape-main")
    print("Skills: stayscape-product-generator, stayscape-visitor-matcher")


if __name__ == "__main__":
    main()
