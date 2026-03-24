from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "dev"
    supabase_db_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/postgres"
    supabase_schema: str = "thesis"
    tavily_api_key: str = ""
    tavily_base_url: str = "https://api.tavily.com"
    bocha_api_key: str = ""
    bocha_base_url: str = "https://api.bochaai.com/v1/web-search"
    macro_intel_timeout_seconds: float = 15.0
    macro_intel_config_path: str = "macro/config/macro_intel.yaml"


settings = Settings()
