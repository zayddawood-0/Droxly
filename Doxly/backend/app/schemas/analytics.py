"""api.md §9 (/analytics) request/response shapes — tasks/remediation-plan.md R9."""

from datetime import date
from typing import Literal

from pydantic import BaseModel

AnalyticsPeriod = Literal["7d", "30d", "90d"]


class TimeSeriesPoint(BaseModel):
    date: date
    count: int


class FeatureUsage(BaseModel):
    feature: str
    count: int


class AnalyticsDashboardResponse(BaseModel):
    documents_processed: int
    documents_over_time: list[TimeSeriesPoint]
    ai_requests: int
    ai_requests_over_time: list[TimeSeriesPoint]
    storage_used_bytes: int
    most_used_features: list[FeatureUsage]
