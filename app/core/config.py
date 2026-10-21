from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database settings
    DATABASE_URL: str
    
    # Authentication settings
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Security settings (CORS, rate limiting)
    CORS_ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:8080"  # Comma-separated list
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: str = "GET,POST,PUT,DELETE,PATCH,OPTIONS"
    CORS_ALLOW_HEADERS: str = "Authorization,Content-Type,X-Requested-With,Accept"
    
    # Rate limiting settings
    RATE_LIMIT_ENABLED: bool = True
    DEFAULT_RATE_LIMIT: str = "100/hour"  # Default rate limit per IP
    
    # Sentry DSN for error tracking (optional)
    SENTRY_DSN: str | None = None
    
    # Redis URL for production rate limiting
    REDIS_URL: str | None = None
    
    # Environment settings
    ENVIRONMENT: str = "development"  # development, production
    DEBUG: bool = False
    
    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()