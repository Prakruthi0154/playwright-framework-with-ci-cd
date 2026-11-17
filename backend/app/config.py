from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "sqlite:///./casecraft.db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret_key: str = "development-secret-change-before-deploy-32-bytes"
    jwt_access_minutes: int = 15
    jwt_refresh_days: int = 14
    cookie_secure: bool = False
    cookie_samesite: Literal["strict", "lax", "none"] = "lax"
    frontend_origins: str = "http://localhost:4200"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    sentry_dsn: str = ""
    upload_max_bytes: int = 15 * 1024 * 1024
    rate_limit_per_minute: int = 120

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def validate_production_security(self):
        if self.app_env == "production":
            if len(self.jwt_secret_key) < 32 or self.jwt_secret_key.startswith("development-"):
                raise ValueError("JWT_SECRET_KEY must be a unique secret of at least 32 characters")
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be enabled in production")
            if self.cookie_samesite == "none" and not self.cookie_secure:
                raise ValueError("SameSite=None cookies require COOKIE_SECURE=true")
            if not self.cors_origins or "*" in self.cors_origins:
                raise ValueError("Production CORS origins must be explicit")
        return self

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.frontend_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
