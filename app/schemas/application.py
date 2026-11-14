"""API schemas for prepared applications and review issues."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.documents.reviewer import Issue
from app.schemas.enums import ApplicationStatus


class ApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    cv_id: str | None
    letter_text: str | None
    review_issues: list[Issue] = Field(default_factory=list)
    status: ApplicationStatus
    notes: str | None
    created_at: datetime
    updated_at: datetime
    sent_at: datetime | None
    cv_choice_reason: str | None = None


class ApplicationEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    from_status: ApplicationStatus | None
    to_status: ApplicationStatus
    note: str | None
    created_at: datetime


class ApproveRequest(BaseModel):
    eligibility_checked: bool = False
    note: str | None = None


class SkipRequest(BaseModel):
    note: str | None = None


class StatusChangeRequest(BaseModel):
    status: ApplicationStatus
    note: str | None = None


class ApplicationWeekCount(BaseModel):
    week: str
    count: int


class StatsRead(BaseModel):
    applications_by_status: dict[str, int]
    matches_by_decision: dict[str, int]
    average_final_score: float | None
    applications_per_week: list[ApplicationWeekCount]
