from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql://stotto:stotto_secret@localhost:5432/stotto"

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"

    # API-Football
    api_football_key: str = ""
    api_football_base_url: str = "https://v3.football.api-sports.io"

    # JWT
    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    # App
    environment: str = "development"
    log_level: str = "INFO"


settings = Settings()
