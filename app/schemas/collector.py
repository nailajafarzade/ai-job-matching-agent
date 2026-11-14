"""Request and response models for collector runs."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CollectorRunRequest(BaseModel):
    search: str | None = None
    limit: int = Field(default=50, ge=1, le=200)


class CollectorSummaryRead(BaseModel):
    fetched: int
    new: int
    duplicates: int
    rejected: int
    needs_review: int
    below_threshold: int
    queued: int


class CollectorRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    started_at: datetime
    finished_at: datetime | None
    fetched: int
    new_jobs: int
    duplicates: int
    error: str | None
