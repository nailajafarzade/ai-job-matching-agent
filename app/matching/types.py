"""Input and output types of the matching step."""
from pydantic import BaseModel, Field

from app.db.models import Match
from app.schemas.enums import MatchDecision, RemoteEligibility, RemoteType


class JobFacts(BaseModel):
    """What the matcher needs to know about a job."""

    title: str
    description: str
    country: str | None = None
    location: str | None = None
    remote_type: RemoteType = RemoteType.unknown
    eligible_countries: list[str] = Field(default_factory=list)
    remote_work_eligibility: RemoteEligibility = RemoteEligibility.unknown
    location_restrictions: str | None = None


class MatchResult(BaseModel):
    decision: MatchDecision
    reject_reasons: list[str] = Field(default_factory=list)
    review_reasons: list[str] = Field(default_factory=list)

    # 0-100. All None when the hard filter rejected the job.
    final_score: float | None = None
    skill_score: float | None = None
    semantic_score: float | None = None
    title_score: float | None = None

    matched_skills: list[str] = Field(default_factory=list)   # I know them hands-on
    studied_skills: list[str] = Field(default_factory=list)   # I only studied them
    missing_skills: list[str] = Field(default_factory=list)   # never added to the profile
    explanation: str = ""

    profile_version: int
    matcher_version: str
    embedding_model: str | None = None
    weights: dict[str, float] = Field(default_factory=dict)

    def to_orm(self, job_id: int, analysis_id: int | None = None) -> Match:
        return Match(job_id=job_id, analysis_id=analysis_id, **self.model_dump(mode="json"))
