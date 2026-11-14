from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.vocabulary import get_vocabulary
from app.db.models import Application, ApplicationEvent, Job, Match
from app.db.session import Base, make_engine
from app.documents.cv_registry import CvEntry, CvRegistry
from app.documents.letter import TemplateLetterWriter
from app.profile.loader import load_profile
from app.services.runtime import DocumentServices
from app.services.sending import prepare_package
from app.senders.base import SenderError
from app.senders.manual import ManualPackageSender

PROFILE = Path(__file__).parent.parent / "data" / "profile.yaml"


@pytest.fixture()
def session():
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session
    engine.dispose()


def make_approved_application(session: Session, company: str = 'Example <> "Company"') -> Application:
    job = Job(
        title="Junior Java Backend Developer",
        company=company,
        url="https://example.test/jobs/123",
        source="manual",
        description_raw="A sufficiently long job description for packaging tests.",
        content_hash=f"hash-{company}",
    )
    session.add(job)
    session.flush()
    application = Application(
        job_id=job.id,
        cv_id="java_backend",
        letter_text="A reviewed application letter.",
        review_issues=[],
        status="approved",
    )
    session.add(application)
    session.add(
        Match(
            job_id=job.id,
            decision="queued",
            explanation="Strong match for Java and Spring Boot.",
            profile_version=3,
            matcher_version="0.1",
        )
    )
    session.commit()
    return application


def make_documents(cv_path: Path) -> DocumentServices:
    vocabulary = get_vocabulary()
    profile = load_profile(PROFILE, vocabulary)
    registry = CvRegistry([CvEntry("java_backend", cv_path, [], [])], [])
    return DocumentServices(profile, vocabulary, registry, TemplateLetterWriter())


def test_manual_package_copies_cv_and_records_package_ready(session, tmp_path):
    application = make_approved_application(session)
    cv_path = tmp_path / "java-cv.pdf"
    cv_path.write_bytes(b"sample pdf content")
    outbox = tmp_path / "outbox"
    documents = make_documents(cv_path)

    result = prepare_package(
        session,
        application,
        documents,
        ManualPackageSender(outbox, "Strong match for Java and Spring Boot."),
    )

    assert application.status == "package_ready"
    assert (result.path / "java-cv.pdf").read_bytes() == b"sample pdf content"
    assert (result.path / "letter.txt").read_text(encoding="utf-8") == application.letter_text
    job_text = (result.path / "job.txt").read_text(encoding="utf-8")
    assert "Title: Junior Java Backend Developer" in job_text
    assert "Company: Example <> \"Company\"" in job_text
    assert "https://example.test/jobs/123" in job_text
    assert "Source: manual" in job_text
    assert "Strong match for Java and Spring Boot." in job_text
    assert (result.path / "README.txt").read_text(encoding="utf-8").startswith("Apply here: https://example.test/jobs/123")
    event = session.scalar(
        select(ApplicationEvent).where(ApplicationEvent.application_id == application.id)
    )
    assert (event.from_status, event.to_status) == ("approved", "package_ready")


def test_manual_package_notes_a_missing_cv_and_still_creates_package(session, tmp_path):
    application = make_approved_application(session, "Missing CV Co")
    missing_cv = tmp_path / "not-present.pdf"

    result = prepare_package(
        session,
        application,
        make_documents(missing_cv),
        ManualPackageSender(tmp_path / "outbox"),
    )

    assert result.path.is_dir()
    assert not (result.path / missing_cv.name).exists()
    assert "Selected CV PDF is missing" in (result.path / "README.txt").read_text(encoding="utf-8")
    assert "was missing" in result.message
    assert application.status == "package_ready"


def test_manual_package_refuses_an_unapproved_application(session, tmp_path):
    application = make_approved_application(session)
    application.status = "prepared"
    session.commit()

    with pytest.raises(SenderError, match="Only approved"):
        prepare_package(session, application, make_documents(tmp_path / "cv.pdf"))