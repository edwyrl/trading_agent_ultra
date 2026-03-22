from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from contracts.enums import SwLevel


class VersionInfoDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    as_of_date: date
    created_at: datetime


class UpdateMetaDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    last_updated_at: datetime
    last_news_update_at: datetime | None = None
    last_market_data_update_at: datetime | None = None
    last_full_refresh_at: datetime | None = None


class TimeRangeDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_date: date
    end_date: date


class SwIndustryRefDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sw_level: SwLevel
    industry_id: str
    industry_name: str
