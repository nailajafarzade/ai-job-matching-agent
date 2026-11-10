"""Response schemas for the job and profile API."""
from pydantic import BaseModel

from app.schemas.analysis import JobAnalysisRead
from app.schemas.job import JobRead
from app.schemas.match import MatchRead


class JobResult(BaseModel):
    duplicate: bool
    job: JobRead
    analysis: JobAnalysisRead | None
    match: MatchRead | None


class ProfileSummary(BaseModel):
    version: int
    skills: dict[str, str]
    target_roles: list[str]
    max_years_required: int
    reject_seniority: list[str]
    excluded_job_countries: list[str]


class ReloadResult(BaseModel):
    old_version: int
    new_version: int
