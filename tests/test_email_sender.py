from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.vocabulary import get_vocabulary
from app.db.models import Application, ApplicationEvent, Job
from app.db.session import Base, make_engine
from app.documents.cv_registry import CvEntry, CvRegistry
from app.documents.letter import TemplateLetterWriter
from app.profile.loader import load_profile
from app.services.runtime import DocumentServices
from app.services.sending import send_email
from app.senders.base import SenderError
from app.senders.email import EmailSender
from app.senders.settings import EmailSettings

PROFILE = Path(__file__).parent.parent / "data" / "profile.yaml"


@pytest.fixture()
def session():
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session
    engine.dispose()


def make_approved_application(session: Session, company: str = "Email Example", apply_email: str | None = "apply@example.test"):
    job = Job(
        title="Junior Java Backend Developer",
        company=company,
        url="https://example.test/jobs/123",
        source="manual",
        apply_email=apply_email,
        description_raw="A sufficiently long job description for email tests.",
        content_hash=f"email-hash-{company}",
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
    session.commit()
    return application


def make_documents(cv_path: Path) -> DocumentServices:
    vocabulary = get_vocabulary()
    profile = load_profile(PROFILE, vocabulary)
    registry = CvRegistry([CvEntry("java_backend", cv_path, [], [])], [])
    return DocumentServices(profile, vocabulary, registry, TemplateLetterWriter())


def test_email_settings_read_local_file_and_prefer_environment(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "SMTP_HOST=file.smtp.test\nSMTP_PORT=587\nSMTP_PASSWORD=file-secret\nEMAIL_DRY_RUN=true\n",
        encoding="utf-8",
    )

    settings = EmailSettings.from_env(
        env_file,
        {
            "SMTP_HOST": "environment.smtp.test",
            "SMTP_PASSWORD": "environment-secret",
            "EMAIL_FROM": "owner@example.test",
        },
    )

    assert settings.smtp_host == "environment.smtp.test"
    assert settings.smtp_port == 587
    assert settings.smtp_password == "environment-secret"
    assert settings.email_from == "owner@example.test"
    assert settings.dry_run is True
    assert "environment-secret" not in repr(settings)


def test_dry_run_writes_eml_and_never_connects(session, tmp_path, monkeypatch, caplog):
    application = make_approved_application(session)
    cv_path = tmp_path / "selected-cv.pdf"
    cv_path.write_bytes(b"selected pdf bytes")

    def forbidden_smtp(*args, **kwargs):
        raise AssertionError("dry-run must not construct an SMTP client")

    monkeypatch.setattr("app.senders.email.smtplib.SMTP", forbidden_smtp)
    secret = "smtp-secret-for-test"
    settings = EmailSettings(email_from="owner@example.test", smtp_password=secret, dry_run=True)
    result = send_email(
        session,
        application,
        make_documents(cv_path),
        settings=settings,
        sender=EmailSender(settings, tmp_path / "outbox"),
    )

    parsed = BytesParser(policy=policy.default).parsebytes(result.path.read_bytes())
    attachments = list(parsed.iter_attachments())
    assert application.status == "package_ready"
    assert result.mode == "dry_run"
    assert "apply@example.test" == parsed["To"]
    assert parsed["Subject"] == "Application: Junior Java Backend Developer"
    assert parsed.get_body(preferencelist=("plain",)).get_content().strip() == application.letter_text
    assert len(attachments) == 1
    assert attachments[0].get_filename() == "selected-cv.pdf"
    assert attachments[0].get_content() == b"selected pdf bytes"
    assert secret.encode() not in result.path.read_bytes()
    assert secret not in result.message
    assert secret not in repr(settings)
    assert secret not in caplog.text


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.message = None
        self.login_values = None
        self.__class__.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def ehlo(self):
        return None

    def starttls(self):
        return None

    def login(self, username, password):
        self.login_values = (username, password)

    def send_message(self, message):
        self.message = message


def test_real_send_uses_tls_updates_status_and_refuses_a_second_send(session, tmp_path, monkeypatch):
    application = make_approved_application(session)
    cv_path = tmp_path / "selected-cv.pdf"
    cv_path.write_bytes(b"selected pdf bytes")
    FakeSMTP.instances.clear()
    monkeypatch.setattr("app.senders.email.smtplib.SMTP", FakeSMTP)
    settings = EmailSettings(
        smtp_host="smtp.example.test",
        smtp_port=587,
        smtp_user="user@example.test",
        smtp_password="do-not-print-this",
        email_from="owner@example.test",
        dry_run=False,
    )
    documents = make_documents(cv_path)

    result = send_email(session, application, documents, settings=settings)

    assert result.status == "sent"
    assert application.status == "sent"
    assert application.sent_at is not None
    assert FakeSMTP.instances[0].login_values == ("user@example.test", "do-not-print-this")
    assert FakeSMTP.instances[0].message["To"] == "apply@example.test"
    assert len(list(FakeSMTP.instances[0].message.iter_attachments())) == 1
    events = session.scalars(
        select(ApplicationEvent).where(ApplicationEvent.application_id == application.id)
    ).all()
    assert [event.to_status for event in events] == ["sent"]

    with pytest.raises(SenderError, match="already been sent"):
        send_email(session, application, documents, settings=settings)
    assert len(FakeSMTP.instances) == 1


def test_real_send_errors_do_not_expose_smtp_password(session, tmp_path, monkeypatch, caplog):
    application = make_approved_application(session, "SMTP Failure Co")
    cv_path = tmp_path / "cv.pdf"
    cv_path.write_bytes(b"pdf")
    secret = "private-smtp-password"

    class BrokenSMTP(FakeSMTP):
        def login(self, username, password):
            raise RuntimeError(f"server rejected {password}")

    monkeypatch.setattr("app.senders.email.smtplib.SMTP", BrokenSMTP)
    settings = EmailSettings(
        smtp_host="smtp.example.test",
        smtp_port=587,
        smtp_user="user@example.test",
        smtp_password=secret,
        email_from="owner@example.test",
        dry_run=False,
    )

    with pytest.raises(SenderError) as error:
        send_email(session, application, make_documents(cv_path), settings=settings)

    assert secret not in str(error.value)
    assert secret not in repr(settings)
    assert secret not in caplog.text
    assert application.status == "approved"


def test_email_requires_approval_recipient_and_cv(session, tmp_path):
    application = make_approved_application(session, "Email Checks Co", apply_email=None)
    cv_path = tmp_path / "cv.pdf"
    cv_path.write_bytes(b"pdf")
    documents = make_documents(cv_path)
    settings = EmailSettings(email_from="owner@example.test", dry_run=True)

    with pytest.raises(SenderError, match="no application email"):
        send_email(session, application, documents, settings=settings)

    job = session.get(Job, application.job_id)
    job.apply_email = "apply@example.test"
    application.status = "prepared"
    session.commit()
    with pytest.raises(SenderError, match="Only approved"):
        send_email(session, application, documents, settings=settings)

    application.status = "approved"
    session.commit()
    missing_documents = make_documents(tmp_path / "missing.pdf")
    with pytest.raises(SenderError, match="CV PDF is missing"):
        send_email(session, application, missing_documents, settings=settings)


def test_real_email_limit_blocks_the_eleventh_send(session, tmp_path):
    application = make_approved_application(session, "Limited Send Co")
    cv_path = tmp_path / "cv.pdf"
    cv_path.write_bytes(b"pdf")
    now = datetime.now(timezone.utc)
    for index in range(10):
        job = Job(
            title=f"Sent Job {index}",
            company=f"Sent Company {index}",
            description_raw="A sent job description for email limit testing.",
            content_hash=f"sent-hash-{index}",
        )
        session.add(job)
        session.flush()
        sent_application = Application(job_id=job.id, status="sent")
        session.add(sent_application)
        session.flush()
        session.add(
            ApplicationEvent(
                application_id=sent_application.id,
                from_status="approved",
                to_status="sent",
                created_at=now - timedelta(minutes=index),
            )
        )
    session.commit()

    class SenderSpy:
        called = False

        def send(self, application_arg, job_arg, cv_path_arg):
            self.called = True
            raise AssertionError("the daily limit should block before sending")

    sender = SenderSpy()
    settings = EmailSettings(email_from="owner@example.test", dry_run=False)
    with pytest.raises(SenderError, match="Daily email limit reached"):
        send_email(session, application, make_documents(cv_path), settings, sender=sender, now=now)
    assert sender.called is False