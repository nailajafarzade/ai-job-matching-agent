import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Job, JobAnalysis, Match
from app.db.session import Base, make_engine
from app.intake.hashing import compute_content_hash
from app.schemas.enums import JobStatus, MatchDecision, RemoteEligibility
from app.schemas.job import JobRead
from app.schemas.match import MatchRead


@pytest.fixture()
def session():
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def make_job(title="Java Developer", company="Acme", text="Junior Java role with Spring Boot.") -> Job:
    return Job(
        title=title,
        company=company,
        description_raw=text,
        content_hash=compute_content_hash(company, title, text),
    )


def test_job_defaults(session):
    job = make_job()
    session.add(job)
    session.commit()
    assert job.source == "manual"
    assert job.status == JobStatus.new.value
    assert job.remote_work_eligibility == RemoteEligibility.unknown.value
    assert job.eligible_countries == []
    assert job.created_at is not None


def test_duplicate_content_hash_is_rejected(session):
    session.add(make_job())
    session.commit()
    session.add(make_job())
    with pytest.raises(IntegrityError):
        session.commit()


def test_analysis_and_match_are_linked_and_versioned(session):
    job = make_job()
    job.analyses.append(
        JobAnalysis(analyzer_version="0.1", required_skills=["Java", "Spring Boot"], min_years=1, seniority="junior")
    )
    session.add(job)
    session.commit()

    match = Match(
        job_id=job.id,
        analysis_id=job.analyses[0].id,
        decision=MatchDecision.queued.value,
        final_score=82.5,
        skill_score=90.0,
        semantic_score=75.0,
        title_score=80.0,
        matched_skills=["Java", "Spring Boot"],
        missing_skills=["Kafka"],
        explanation="Matches: Java, Spring Boot. Missing: Kafka.",
        profile_version=3,
        matcher_version="0.1",
        embedding_model="all-MiniLM-L6-v2",
        weights={"skill": 0.45, "semantic": 0.35, "title": 0.20},
    )
    session.add(match)
    session.commit()

    loaded = session.scalars(select(Match)).one()
    assert loaded.job.title == "Java Developer"
    assert loaded.missing_skills == ["Kafka"]
    assert loaded.profile_version == 3
    assert loaded.weights["skill"] == 0.45


def test_rejected_match_can_have_no_scores(session):
    job = make_job()
    session.add(job)
    session.commit()
    session.add(
        Match(
            job_id=job.id,
            decision=MatchDecision.rejected.value,
            reject_reasons=["Seniority: senior"],
            profile_version=3,
            matcher_version="0.1",
        )
    )
    session.commit()
    loaded = session.scalars(select(Match)).one()
    assert loaded.final_score is None
    assert loaded.reject_reasons == ["Seniority: senior"]


def test_same_analyzer_version_twice_is_rejected(session):
    job = make_job()
    job.analyses.append(JobAnalysis(analyzer_version="0.1"))
    session.add(job)
    session.commit()
    session.add(JobAnalysis(job_id=job.id, analyzer_version="0.1"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_deleting_a_job_deletes_its_analyses_and_matches(session):
    job = make_job()
    job.analyses.append(JobAnalysis(analyzer_version="0.1"))
    job.matches.append(Match(profile_version=3, matcher_version="0.1"))
    session.add(job)
    session.commit()
    session.delete(job)
    session.commit()
    assert session.scalars(select(JobAnalysis)).all() == []
    assert session.scalars(select(Match)).all() == []


def test_orm_objects_convert_to_schemas(session):
    job = make_job()
    session.add(job)
    session.commit()
    read = JobRead.model_validate(job)
    assert read.title == "Java Developer" and read.status == JobStatus.new

    match = Match(job_id=job.id, decision="queued", final_score=70.0, profile_version=3, matcher_version="0.1")
    session.add(match)
    session.commit()
    assert MatchRead.model_validate(match).decision == MatchDecision.queued


def test_match_schema_rejects_score_over_100(session):
    job = make_job()
    session.add(job)
    session.commit()
    match = Match(job_id=job.id, decision="queued", final_score=130.0, profile_version=3, matcher_version="0.1")
    session.add(match)
    session.commit()
    with pytest.raises(ValidationError):
        MatchRead.model_validate(match)
