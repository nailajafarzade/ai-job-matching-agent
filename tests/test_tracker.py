from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Application, ApplicationEvent, Job, Match
from app.db.session import Base, make_engine
from app.intake.hashing import compute_content_hash
from app.services.tracker import (
    ALLOWED,
    ApprovalRefusedError,
    InvalidTransitionError,
    approve,
    change_status,
)


@pytest.fixture()
def session():
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session
    engine.dispose()


EXPECTED_TRANSITIONS = {
    "prepared": {"approved", "skipped"},
    "approved": {"package_ready", "sent", "skipped", "prepared"},
    "package_ready": {"sent", "skipped"},
    "sent": {"replied", "interview", "rejected", "withdrawn"},
    "replied": {"interview", "rejected", "withdrawn"},
    "interview": {"rejected", "withdrawn"},
    "skipped": {"prepared"},
    "rejected": set(),
    "withdrawn": set(),
}


def make_application(session: Session, status: str = "prepared", **overrides) -> Application:
    number = session.query(Application).count()
    title = f"Job {number}"
    company = f"Company {number}"
    description = "A sufficiently long job description for a test application."
    job = Job(
        title=title,
        company=company,
        description_raw=description,
        content_hash=compute_content_hash(company, title, description),
    )
    session.add(job)
    session.flush()
    values = {
        "job_id": job.id,
        "status": status,
        "cv_id": "java_backend",
        "letter_text": "A reviewed application letter.",
        "review_issues": [],
    }
    values.update(overrides)
    application = Application(**values)
    session.add(application)
    session.commit()
    return application


def add_match(session: Session, application: Application, decision: str) -> None:
    session.add(
        Match(
            job_id=application.job_id,
            decision=decision,
            profile_version=3,
            matcher_version="0.1",
        )
    )
    session.commit()


def test_allowed_transition_map_is_complete_and_matches_the_status_rules():
    assert ALLOWED == EXPECTED_TRANSITIONS


@pytest.mark.parametrize(
    ("from_status", "to_status"),
    [(source, target) for source, targets in EXPECTED_TRANSITIONS.items() for target in targets],
)
def test_every_allowed_transition_records_an_event(session, from_status, to_status):
    application = make_application(session, status=from_status)

    change_status(session, application, to_status, note="Moved by owner")
    session.commit()

    event = session.scalars(
        select(ApplicationEvent).where(ApplicationEvent.application_id == application.id)
    ).one()
    assert application.status == to_status
    assert (event.from_status, event.to_status, event.note) == (from_status, to_status, "Moved by owner")
    if to_status == "sent":
        assert isinstance(application.sent_at, datetime)


def test_every_illegal_transition_is_rejected_without_an_event(session):
    statuses = list(EXPECTED_TRANSITIONS)
    for from_status, targets in EXPECTED_TRANSITIONS.items():
        for to_status in set(statuses) - targets:
            application = make_application(session, status=from_status)

            with pytest.raises(InvalidTransitionError):
                change_status(session, application, to_status)

            assert application.status == from_status
            assert application.events == []


def test_approval_reports_all_refusal_reasons(session):
    application = make_application(
        session,
        cv_id=None,
        letter_text=None,
        review_issues=[{"level": "error", "message": "Unsupported skill"}],
    )
    add_match(session, application, "needs_review")

    with pytest.raises(ApprovalRefusedError) as raised:
        approve(session, application)

    message = str(raised.value)
    assert "review" in message.lower()
    assert "eligibility_checked" in message
    assert "letter" in message.lower()
    assert "CV" in message
    assert application.status == "prepared"


def test_approval_of_needs_review_requires_eligibility_confirmation(session):
    application = make_application(session)
    add_match(session, application, "needs_review")

    with pytest.raises(ApprovalRefusedError, match="eligibility_checked"):
        approve(session, application, eligibility_checked=False)

    approved = approve(session, application, eligibility_checked=True, note="Eligibility checked")
    session.commit()

    assert approved.status == "approved"
    assert approved.events[-1].note == "Eligibility checked"


def test_approval_of_clean_queued_application_succeeds(session):
    application = make_application(session)
    add_match(session, application, "queued")

    approve(session, application)
    session.commit()

    assert application.status == "approved"
