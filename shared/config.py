from __future__ import annotations

from functools import cached_property

from pydantic import BaseModel, ConfigDict
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    db_url: str
    schema_name: str


class SearchProviderSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: str
    base_url: str


class SearchSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tavily: SearchProviderSettings
    bocha: SearchProviderSettings


class LLMProviderSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: str
    base_url: str


class LLMSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    models_config_path: str
    openai: LLMProviderSettings
    anthropic: LLMProviderSettings
    moonshot: LLMProviderSettings
    siliconflow: LLMProviderSettings


class MacroIntelSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeout_seconds: float
    config_path: str
    event_log_path: str
    eval_pack_path: str
    editor_role: str
    editor_timeout_seconds: float
    summarizer_role: str
    summarizer_timeout_seconds: float


class EmailSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: str
    base_url: str
    from_email: str
    digest_recipients_doc_path: str
    digest_subject_prefix: str
    eval_google_form_url: str
    eval_form_entry_date: str
    eval_form_entry_sample_id: str
    eval_form_entry_selected: str
    eval_form_entry_topic: str
    eval_form_entry_event_id: str
    eval_form_selected_true_value: str
    eval_form_selected_false_value: str


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
    macro_intel_event_log_path: str = "logs/macro_intel_latest.json"
    macro_intel_eval_pack_path: str = "logs/macro_eval_pack_latest.json"
    macro_intel_editor_role: str = "macro_editor"
    macro_intel_editor_timeout_seconds: float = 12.0
    macro_intel_summarizer_role: str = "macro_summarizer"
    macro_intel_summarizer_timeout_seconds: float = 16.0
    llm_models_config_path: str = "shared/config/llm_models.yaml"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com"
    moonshot_api_key: str = ""
    moonshot_base_url: str = "https://api.moonshot.cn/v1"
    siliconflow_api_key: str = ""
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
    resend_api_key: str = ""
    resend_base_url: str = "https://api.resend.com/emails"
    resend_from_email: str = ""
    macro_digest_recipients_doc_path: str = "docs/macro_digest_recipients.md"
    macro_digest_subject_prefix: str = "[Macro Digest]"
    macro_eval_google_form_url: str = ""
    macro_eval_form_entry_date: str = ""
    macro_eval_form_entry_sample_id: str = ""
    macro_eval_form_entry_selected: str = ""
    macro_eval_form_entry_topic: str = ""
    macro_eval_form_entry_event_id: str = ""
    macro_eval_form_selected_true_value: str = "True"
    macro_eval_form_selected_false_value: str = "False"
    tushare_api_key: str = ""
    tushare_base_url: str = "http://api.tushare.pro"
    tushare_timeout_seconds: float = 30.0
    tushare_page_size: int = 5000
    tushare_retry_max_attempts: int = 3
    tushare_retry_delay_seconds: float = 30.0
    tushare_max_pages: int = 200

    @cached_property
    def database(self) -> DatabaseSettings:
        return DatabaseSettings(
            db_url=self.supabase_db_url,
            schema_name=self.supabase_schema,
        )

    @cached_property
    def search(self) -> SearchSettings:
        return SearchSettings(
            tavily=SearchProviderSettings(
                api_key=self.tavily_api_key,
                base_url=self.tavily_base_url,
            ),
            bocha=SearchProviderSettings(
                api_key=self.bocha_api_key,
                base_url=self.bocha_base_url,
            ),
        )

    @cached_property
    def llm(self) -> LLMSettings:
        return LLMSettings(
            models_config_path=self.llm_models_config_path,
            openai=LLMProviderSettings(
                api_key=self.openai_api_key,
                base_url=self.openai_base_url,
            ),
            anthropic=LLMProviderSettings(
                api_key=self.anthropic_api_key,
                base_url=self.anthropic_base_url,
            ),
            moonshot=LLMProviderSettings(
                api_key=self.moonshot_api_key,
                base_url=self.moonshot_base_url,
            ),
            siliconflow=LLMProviderSettings(
                api_key=self.siliconflow_api_key,
                base_url=self.siliconflow_base_url,
            ),
        )

    @cached_property
    def macro_intel(self) -> MacroIntelSettings:
        return MacroIntelSettings(
            timeout_seconds=self.macro_intel_timeout_seconds,
            config_path=self.macro_intel_config_path,
            event_log_path=self.macro_intel_event_log_path,
            eval_pack_path=self.macro_intel_eval_pack_path,
            editor_role=self.macro_intel_editor_role,
            editor_timeout_seconds=self.macro_intel_editor_timeout_seconds,
            summarizer_role=self.macro_intel_summarizer_role,
            summarizer_timeout_seconds=self.macro_intel_summarizer_timeout_seconds,
        )

    @cached_property
    def email(self) -> EmailSettings:
        return EmailSettings(
            api_key=self.resend_api_key,
            base_url=self.resend_base_url,
            from_email=self.resend_from_email,
            digest_recipients_doc_path=self.macro_digest_recipients_doc_path,
            digest_subject_prefix=self.macro_digest_subject_prefix,
            eval_google_form_url=self.macro_eval_google_form_url,
            eval_form_entry_date=self.macro_eval_form_entry_date,
            eval_form_entry_sample_id=self.macro_eval_form_entry_sample_id,
            eval_form_entry_selected=self.macro_eval_form_entry_selected,
            eval_form_entry_topic=self.macro_eval_form_entry_topic,
            eval_form_entry_event_id=self.macro_eval_form_entry_event_id,
            eval_form_selected_true_value=self.macro_eval_form_selected_true_value,
            eval_form_selected_false_value=self.macro_eval_form_selected_false_value,
        )


settings = Settings()
