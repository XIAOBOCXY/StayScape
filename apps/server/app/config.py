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
    openclaw_model: str = "openclaw/default"

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
