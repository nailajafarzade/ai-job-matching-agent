"""Schemas for the job analysis result."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.enums import Seniority


class AnalysisResult(BaseModel):
    """What the analyzer returns for one job text."""

    required_skills: list[str] = Field(default_factory=list)
    nice_to_have_skills: list[str] = Field(default_factory=list)
    min_years: int | None = Field(default=None, ge=0, le=50, description="None = not stated")
    seniority: Seniority = Seniority.unknown


class JobAnalysisRead(AnalysisResult):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    analyzer_version: str
    created_at: datetime
