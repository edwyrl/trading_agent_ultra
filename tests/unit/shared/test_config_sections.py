from __future__ import annotations

from shared.config import settings


def test_settings_section_views_map_to_flat_fields() -> None:
    assert settings.database.db_url == settings.supabase_db_url
    assert settings.database.schema_name == settings.supabase_schema

    assert settings.search.tavily.api_key == settings.tavily_api_key
    assert settings.search.tavily.base_url == settings.tavily_base_url
    assert settings.search.bocha.api_key == settings.bocha_api_key
    assert settings.search.bocha.base_url == settings.bocha_base_url

    assert settings.llm.models_config_path == settings.llm_models_config_path
    assert settings.llm.openai.base_url == settings.openai_base_url
    assert settings.llm.anthropic.base_url == settings.anthropic_base_url
    assert settings.llm.moonshot.base_url == settings.moonshot_base_url
    assert settings.llm.siliconflow.base_url == settings.siliconflow_base_url

    assert settings.macro_intel.timeout_seconds == settings.macro_intel_timeout_seconds
    assert settings.macro_intel.config_path == settings.macro_intel_config_path
    assert settings.macro_intel.event_log_path == settings.macro_intel_event_log_path

    assert settings.email.api_key == settings.resend_api_key
    assert settings.email.base_url == settings.resend_base_url
    assert settings.email.from_email == settings.resend_from_email


def test_settings_section_views_are_cached() -> None:
    assert settings.database is settings.database
    assert settings.search is settings.search
    assert settings.llm is settings.llm
    assert settings.macro_intel is settings.macro_intel
    assert settings.email is settings.email
