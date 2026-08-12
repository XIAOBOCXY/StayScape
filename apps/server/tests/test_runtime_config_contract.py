import json
import os
import subprocess
import sys
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
RENDER = ROOT / "scripts" / "render_openclaw_config.py"


def render(**overrides):
    # Some Windows workstations have a locked or non-ASCII pytest TEMP root.
    # Keep this contract test independent of pytest's tmp_path fixture while
    # still ensuring every subprocess gets an isolated output file.
    output = ROOT / f".pytest-openclaw-config-{uuid.uuid4().hex}.json"
    env = os.environ.copy()
    env.update(
        {
            "OPENCLAW_GATEWAY_TOKEN": "gateway-test-token",
            "STAYSCAPE_AGENT_TOOL_TOKEN": "tool-test-token",
            "OPENCLAW_CONFIG_PATH": str(output),
            "OPENCLAW_PRIMARY_MODEL": "qwen/qwen3.5-plus",
            "FEISHU_APP_ID": "cli_test",
            "FEISHU_APP_SECRET": "secret-test",
        }
    )
    env.update(overrides)
    try:
        subprocess.run([sys.executable, str(RENDER)], cwd=ROOT, env=env, check=True, capture_output=True, text=True)
        return json.loads(output.read_text(encoding="utf-8"))
    finally:
        output.unlink(missing_ok=True)


def test_model_target_and_primary_model_are_separate():
    config = render(OPENCLAW_AGENT_TARGET="openclaw/default")
    assert config["agents"]["defaults"]["model"]["primary"] == "qwen/qwen3.5-plus"
    assert "OPENCLAW_AGENT_TARGET" not in json.dumps(config)


def test_feishu_credentials_do_not_override_explicit_disabled_switch():
    config = render(FEISHU_ENABLED="false")
    assert config["channels"]["feishu"]["enabled"] is False
    assert config["plugins"]["entries"]["feishu"]["enabled"] is False


def test_feishu_requires_enabled_switch_and_credentials():
    config = render(FEISHU_ENABLED="true", FEISHU_DM_ALLOW_FROM="ou_operator")
    assert config["channels"]["feishu"]["enabled"] is True
    assert config["channels"]["feishu"]["allowFrom"] == ["ou_operator"]


def test_config_loads_official_runtime_plugins_and_no_static_sender():
    config = render()
    assert "qwen" in config["plugins"]["allow"]
    assert "feishu" in config["plugins"]["allow"]
    assert "senderId" not in json.dumps(config["plugins"]["entries"]["stayscape-openclaw-plugin"])
