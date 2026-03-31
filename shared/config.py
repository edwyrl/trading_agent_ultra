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
    llm_models_config_path: str = "shared/config/llm_models.yaml"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com"
    moonshot_api_key: str = ""
    moonshot_base_url: str = "https://api.moonshot.cn/v1"
    resend_api_key: str = ""
    resend_base_url: str = "https://api.resend.com/emails"
    resend_from_email: str = ""
    macro_digest_recipients_doc_path: str = "docs/macro_digest_recipients.md"
    macro_digest_subject_prefix: str = "[Macro Digest]"


settings = Settings()
