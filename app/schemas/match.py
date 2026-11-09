"""Schemas for the match result."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.enums import MatchDecision

Score = Field(default=None, ge=0, le=100)


class MatchRead(BaseModel):
    """One match result. Scores are None when the hard filter rejected the job."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    analysis_id: int | None
    decision: MatchDecision
    reject_reasons: list[str]
    review_reasons: list[str]

    final_score: float | None = Score
    skill_score: float | None = Score
    semantic_score: float | None = Score
    title_score: float | None = Score

    matched_skills: list[str]
    studied_skills: list[str]
    missing_skills: list[str]
    explanation: str

    profile_version: int
    matcher_version: str
    embedding_model: str | None
    weights: dict[str, float]
    created_at: datetime
