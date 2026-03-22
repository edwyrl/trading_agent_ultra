from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "dev"
    supabase_db_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/postgres"
    supabase_schema: str = "thesis"


settings = Settings()
