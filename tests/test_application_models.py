import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Application, ApplicationEvent, CollectorRun, Job
from app.db.session import Base, make_engine
from app.intake.hashing import compute_content_hash
from app.schemas.enums import ApplicationStatus


@pytest.fixture()
def session():
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session
    engine.dispose()


def make_job() -> Job:
    title = "Junior Java Developer"
    company = "Example Tech"
    description = "A junior role using Java and Spring Boot."
    return Job(
        title=title,
        company=company,
        description_raw=description,
        content_hash=compute_content_hash(company, title, description),
    )


def test_application_defaults(session):
    job = make_job()
    application = Application(job=job)
    session.add(application)
    session.commit()

    assert application.status == ApplicationStatus.prepared.value
    assert application.review_issues == []
    assert application.created_at is not None
    assert application.updated_at is not None
    assert application.sent_at is None


def test_application_job_id_is_unique(session):
    job = make_job()
    session.add(job)
    session.flush()
    session.add_all([Application(job_id=job.id), Application(job_id=job.id)])
    with pytest.raises(IntegrityError):
        session.commit()


def test_deleting_job_cascades_through_application_events(session):
    job = make_job()
    application = Application(
        job=job,
        events=[ApplicationEvent(from_status=None, to_status=ApplicationStatus.prepared.value)],
    )
    session.add(application)
    session.commit()

    session.delete(job)
    session.commit()

    assert session.scalars(select(Application)).all() == []
    assert session.scalars(select(ApplicationEvent)).all() == []


def test_application_events_keep_insertion_order(session):
    job = make_job()
    application = Application(job=job)
    application.events.extend(
        [
            ApplicationEvent(from_status=None, to_status="prepared"),
            ApplicationEvent(from_status="prepared", to_status="approved"),
            ApplicationEvent(from_status="approved", to_status="sent"),
        ]
    )
    session.add(application)
    session.commit()

    loaded = session.get(Application, application.id)
    assert [event.to_status for event in loaded.events] == ["prepared", "approved", "sent"]


def test_collector_run_defaults(session):
    run = CollectorRun(source="remotive")
    session.add(run)
    session.commit()

    assert run.fetched == 0
    assert run.new_jobs == 0
    assert run.duplicates == 0
    assert run.error is None
    assert run.started_at is not None
