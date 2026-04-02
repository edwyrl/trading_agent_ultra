from __future__ import annotations

from macro.intel.editor import _provider_settings
from shared.llm.models import LLMProvider


def test_provider_settings_supports_siliconflow() -> None:
    api_key, base_url = _provider_settings(LLMProvider.SILICONFLOW)
    assert api_key == ""
    assert base_url.startswith("https://api.siliconflow.cn")
