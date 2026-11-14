"""Schemas for job input and output."""
from datetime import datetime
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.enums import JobStatus, RemoteEligibility, RemoteType


class JobCreate(BaseModel):
    """What I send when I add a job post."""

    source: str = Field(default="manual", min_length=1, max_length=50)
    title: str = Field(min_length=2, max_length=300)
    company: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=30, description="The full text of the job post")
    url: str | None = Field(default=None, max_length=1000)
    location: str | None = Field(default=None, max_length=300)
    country: str | None = Field(default=None, max_length=100)
    remote_type: RemoteType = RemoteType.unknown
    eligible_countries: list[str] = Field(default_factory=list)
    remote_work_eligibility: RemoteEligibility = RemoteEligibility.unknown
    location_restrictions: str | None = None
    apply_email: str | None = None

    @field_validator("source", "title", "company", "description", mode="before")
    @classmethod
    def _strip(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("url", "location", "country", "location_restrictions", "apply_email", mode="before")
    @classmethod
    def _empty_to_none(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("apply_email")
    @classmethod
    def _validate_apply_email(cls, value):
        if value is not None and re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value) is None:
            raise ValueError("apply_email must be a valid email address")
        return value


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    apply_email: str | None
    url: str | None
    title: str
    company: str
    location: str | None
    country: str | None
    remote_type: RemoteType
    eligible_countries: list[str]
    remote_work_eligibility: RemoteEligibility
    location_restrictions: str | None
    status: JobStatus
    created_at: datetime
