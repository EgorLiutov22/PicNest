from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    # extra="ignore": .env содержит переменные, которые читает docker compose
    # (POSTGRES_*, GRAFANA_*, LOG_* и др.), но не само приложение. С настройкой
    # по умолчанию pydantic-settings падает на них с extra_forbidden.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str

    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    CORS_ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:8080"
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: str = "GET,POST,PUT,DELETE,PATCH,OPTIONS"
    CORS_ALLOW_HEADERS: str = "Authorization,Content-Type,X-Requested-With,Accept"

    RATE_LIMIT_ENABLED: bool = True
    DEFAULT_RATE_LIMIT: str = "100/hour"

    SENTRY_DSN: str | None = None

    REDIS_URL: str | None = None

    ENVIRONMENT: str = "development"
    DEBUG: bool = False

    APP_VERSION: str = "1.0.0"
    LOG_LEVEL: str = "INFO"

    # Фоновая чистка просроченных холдов брони.
    OCCUPANCY_SWEEP_ENABLED: bool = True
    OCCUPANCY_SWEEP_INTERVAL_SECONDS: int = 60


@lru_cache()
def get_settings() -> Settings:
    return Settings()
