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
