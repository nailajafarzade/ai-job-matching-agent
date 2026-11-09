import pytest
from pydantic import ValidationError

from app.schemas.analysis import AnalysisResult
from app.schemas.enums import RemoteEligibility, RemoteType, Seniority
from app.schemas.job import JobCreate

LONG_TEXT = "We are looking for a junior Java developer with Spring Boot."


def test_job_create_defaults_and_strips():
    job = JobCreate(title="  Java Developer ", company=" Acme ", description=f"  {LONG_TEXT}  ", url="  ")
    assert job.title == "Java Developer"
    assert job.company == "Acme"
    assert job.description == LONG_TEXT
    assert job.url is None
    assert job.remote_type == RemoteType.unknown
    assert job.remote_work_eligibility == RemoteEligibility.unknown
    assert job.eligible_countries == []


def test_job_create_rejects_short_description():
    with pytest.raises(ValidationError):
        JobCreate(title="Java Developer", company="Acme", description="too short")


def test_job_create_rejects_blank_title():
    with pytest.raises(ValidationError):
        JobCreate(title="   ", company="Acme", description=LONG_TEXT)


def test_job_create_rejects_unknown_remote_type():
    with pytest.raises(ValidationError):
        JobCreate(title="Java Developer", company="Acme", description=LONG_TEXT, remote_type="space")


def test_analysis_defaults():
    result = AnalysisResult()
    assert result.required_skills == []
    assert result.min_years is None
    assert result.seniority == Seniority.unknown


def test_analysis_rejects_negative_years():
    with pytest.raises(ValidationError):
        AnalysisResult(min_years=-1)
