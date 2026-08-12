from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_name: str = "StayScape"
    secret_key: str = "change-me-before-production-32chars"
    access_token_expire_minutes: int = 120

    database_url: str = "sqlite:///./stayscape.db"
    postgres_database_url: str = "postgresql+psycopg://stayscape:stayscape@db:5432/stayscape"

    mode: str = "demo"
    agent_provider: str = "mock"
    agent_timeout_seconds: float = 20
    agent_max_retries: int = 1
    mock_agent_mode: str = "normal"
    openclaw_base_url: str = ""
    openclaw_gateway_token: str = ""
    # OpenResponses routes to the Agent target; OpenClaw itself selects the
    # backend model from agents.defaults.model.primary.
    openclaw_agent_target: str = "openclaw/default"
    openclaw_primary_model: str = "qwen/qwen3.5-plus"
    openclaw_transport: str = "responses"
    openclaw_responses_path: str = "/v1/responses"
    openclaw_agent_id: str = "stayscape-main"
    openclaw_skill_version: str = "1.0.0"
    openclaw_skills_ready: bool = False
    openclaw_runtime_version: str = "2026.6.9"
    # This flag is set only after Gateway, Agent, provider, Skills, tools and
    # a real /v1/responses smoke test all pass in live mode.
    openclaw_live_ready: bool = False
    stayscape_agent_tool_token: str = ""
    feishu_enabled: bool = False
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_dm_allow_from: str = ""
    feishu_group_allow_from: str = ""
    feishu_group_sender_allow_from: str = ""
    feishu_operator_allow_from: str = ""
    feishu_support_allow_from: str = ""
    feishu_require_mention: bool = True
    poster_embed_remote_images: bool = False
    visitor_intent_hold_minutes: int = 30

    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    vite_api_base_url: str = "/api/v1"
    seed_on_startup: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def live_agent_required(self) -> bool:
        return self.mode.lower() == "live" or self.agent_provider.lower() == "openclaw"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
