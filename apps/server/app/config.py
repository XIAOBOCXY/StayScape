from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_name: str = "StayScape"
    secret_key: str = "change-me-before-production-32chars"
    access_token_expire_minutes: int = 120

    database_url: str = "sqlite:///./stayscape.db"
    postgres_database_url: str = "postgresql+psycopg://stayscape:stayscape@db:5432/stayscape"

    agent_provider: str = "mock"
    agent_timeout_seconds: float = 20
    agent_max_retries: int = 1
    mock_agent_mode: str = "normal"
    openclaw_base_url: str = ""
    openclaw_api_key: str = ""
    openclaw_gateway_token: str = ""
    openclaw_model: str = "openclaw/default"
    # ClawHive manages the lobster/Agent runtime. These OPENCLAW_* names are
    # retained for backwards compatibility with local runtime bridges.
    openclaw_transport: str = "responses"
    openclaw_responses_path: str = "/v1/responses"
    openclaw_invoke_path: str = "/tools/invoke"
    openclaw_tool_name: str = "skill_invoke"
    openclaw_session_key: str = "main"
    openclaw_agent_id: str = ""
    openclaw_skill_version: str = "1.0.0"
    openclaw_legacy_fallback: bool = True
    # Preferred ClawHive names. A ClawHive-managed local/cloud Agent bridge
    # can be configured without changing the legacy OPENCLAW_* deployment.
    clawhive_base_url: str = ""
    clawhive_api_key: str = ""
    clawhive_gateway_token: str = ""
    clawhive_model: str = ""
    clawhive_transport: str = "responses"
    clawhive_responses_path: str = "/v1/responses"
    clawhive_agent_id: str = ""
    clawhive_skill_version: str = "1.0.0"
    poster_embed_remote_images: bool = False
    visitor_intent_hold_minutes: int = 30

    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    vite_api_base_url: str = "/api/v1"
    seed_on_startup: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
