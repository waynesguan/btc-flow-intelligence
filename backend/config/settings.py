from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "btcObserver"
    env: str = "dev"
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    postgres_host: str = "db"
    postgres_port: int = 5432
    postgres_db: str = "btc_observer"
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"

    redis_enabled: bool = True
    redis_url: str = "redis://redis:6379/0"

    scheduler_timezone: str = "UTC"
    backfill_on_startup: bool = True

    request_timeout_seconds: int = 20
    rate_limit_per_minute: int = 60

    fred_api_key: Optional[str] = None
    coingecko_api_key: Optional[str] = None
    glassnode_api_key: Optional[str] = None
    coin_metrics_api_key: Optional[str] = None

    cors_origins: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    disclaimer_text: str = "本看板仅供信息参考，不构成任何投资建议。"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> List[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, list):
            return [str(item) for item in value]
        return []


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
