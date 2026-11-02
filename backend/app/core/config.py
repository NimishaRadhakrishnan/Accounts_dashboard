"""Application settings, read from environment variables (see .env.example)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Vishakan Bio Tech — Accounts"
    environment: str = "development"  # development | production

    database_url: str = "postgresql+psycopg2://vbt:vbt_dev@localhost:5432/vbt_accounts"

    # Security
    jwt_secret: str = "change-me-in-production-please-use-a-long-random-string"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    session_idle_minutes: int = 30  # refresh token lifetime, slides on every refresh
    max_failed_logins: int = 5
    lockout_minutes: int = 15
    cookie_secure: bool = False  # True in production (HTTPS behind Cloudflare)

    # Files
    upload_dir: str = "./data/uploads"
    max_upload_mb: int = 5

    # Company defaults (overridden by Settings screen once company data arrives)
    company_state_code: str = "33"  # Tamil Nadu

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
