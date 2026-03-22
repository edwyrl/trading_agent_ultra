from __future__ import annotations


class IndustryRefreshTrigger:
    def should_light_update(self, last_news_update_at) -> bool:
        _ = last_news_update_at
        return False

    def should_market_update(self, last_market_data_update_at) -> bool:
        _ = last_market_data_update_at
        return False
