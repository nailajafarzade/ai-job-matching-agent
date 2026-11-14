from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.collectors.base import CollectorError, CollectorRateLimitError
from app.collectors.runner import run_collector
from app.db.models import CollectorRun
from app.db.session import init_db, make_engine
from app.schemas.enums import RemoteType
from app.schemas.job import JobCreate
from app.services.runtime import build_pipeline
from tests.fakes import HashingEmbedder

PROFILE = Path(__file__).parent.parent / "data" / "profile.yaml"
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


class StaticCollector:
    name = "test-source"

    def __init__(self, jobs=None, error=None):
        self.jobs = jobs or []
        self.error = error

    def fetch(self, search=None, limit=50):
        if self.error:
            raise self.error
        return self.jobs[:limit]


def make_session():
    engine = make_engine("sqlite:///:memory:")
    init_db(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)()


def make_pipeline():
    return build_pipeline(PROFILE, HashingEmbedder(), min_score=0)


def good_job(company="Example Collector"):
    return JobCreate(
        source="test-source",
        title="Junior Java Backend Developer",
        company=company,
        description=(
            "We need a junior Java backend developer. Requirements include Java, Spring Boot, "
            "PostgreSQL and REST API. Build backend services with the team."
        ),
        remote_type=RemoteType.remote,
        eligible_countries=["Worldwide"],
    )


def test_runner_counts_new_job_decisions_and_duplicates():
    engine, session = make_session()
    try:
        collector = StaticCollector([good_job()])
        first = run_collector(session, make_pipeline(), collector, now=NOW)
        second = run_collector(session, make_pipeline(), collector, now=NOW + timedelta(minutes=1))

        assert first.fetched == first.new == first.queued == 1
        assert first.duplicates == 0
        assert second.fetched == second.duplicates == 1
        assert second.new == 0
        runs = session.scalars(select(CollectorRun).order_by(CollectorRun.id)).all()
        assert [(run.fetched, run.new_jobs, run.duplicates) for run in runs] == [(1, 1, 0), (1, 0, 1)]
    finally:
        session.close()
        engine.dispose()


def test_runner_records_failed_fetch_and_raises_clear_error():
    engine, session = make_session()
    try:
        collector = StaticCollector(error=CollectorError("source unavailable"))
        with pytest.raises(CollectorError, match="source unavailable"):
            run_collector(session, make_pipeline(), collector, now=NOW)

        run = session.scalar(select(CollectorRun))
        assert run.error == "source unavailable"
        assert run.finished_at is not None
        assert run.fetched == 0
    finally:
        session.close()
        engine.dispose()


def test_runner_refuses_a_second_run_before_sixty_seconds():
    engine, session = make_session()
    try:
        collector = StaticCollector()
        run_collector(session, make_pipeline(), collector, now=NOW)
        with pytest.raises(CollectorRateLimitError) as error:
            run_collector(session, make_pipeline(), collector, now=NOW + timedelta(seconds=59))

        assert error.value.next_allowed_at == NOW + timedelta(seconds=60)
        assert len(session.scalars(select(CollectorRun)).all()) == 1
        run_collector(session, make_pipeline(), collector, now=NOW + timedelta(seconds=60))
    finally:
        session.close()
        engine.dispose()


def test_runner_refuses_fifth_run_in_24_hours_and_reports_allowed_time():
    engine, session = make_session()
    try:
        collector = StaticCollector()
        for index in range(4):
            run_collector(session, make_pipeline(), collector, now=NOW + timedelta(minutes=index))

        with pytest.raises(CollectorRateLimitError) as error:
            run_collector(session, make_pipeline(), collector, now=NOW + timedelta(minutes=4))

        assert error.value.next_allowed_at == NOW + timedelta(hours=24)
        run_collector(session, make_pipeline(), collector, now=NOW + timedelta(hours=24))
    finally:
        session.close()
        engine.dispose()


def test_runner_continues_after_one_job_fails(monkeypatch):
    engine, session = make_session()
    try:
        pipeline = make_pipeline()
        original_submit = pipeline.submit

        def submit_one_bad_job(session_arg, job):
            if job.company == "Bad Company":
                raise RuntimeError("bad job")
            return original_submit(session_arg, job)

        monkeypatch.setattr(pipeline, "submit", submit_one_bad_job)
        collector = StaticCollector([good_job("Bad Company"), good_job("Good Company")])
        summary = run_collector(session, pipeline, collector, now=NOW)

        assert summary.fetched == 2
        assert summary.new == summary.queued == 1
        assert session.scalar(select(CollectorRun)).error == "bad job"
    finally:
        session.close()
        engine.dispose()
