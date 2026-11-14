"""Prepare manual packages and send only explicitly approved applications."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import MAX_EMAILS_PER_DAY, OUTBOX_DIR
from app.db.models import Application, ApplicationEvent, Job, Match
from app.schemas.enums import ApplicationStatus
from app.senders.base import ApplicationSender, SendResult, SenderError
from app.senders.email import EmailSender
from app.senders.manual import ManualPackageSender
from app.senders.settings import EmailSettings
from app.services.runtime import DocumentServices
from app.services.tracker import change_status


def prepare_package(
    session: Session,
    application: Application,
    documents: DocumentServices,
    sender: ApplicationSender | None = None,
) -> SendResult:
    """Write a manual package for an approved application and update its status."""
    if application.status != ApplicationStatus.approved.value:
        raise SenderError("Only approved applications can be packaged")
    job, cv_path = _job_and_cv(session, application, documents)
    if sender is None:
        match = session.scalar(
            select(Match).where(Match.job_id == job.id).order_by(Match.id.desc()).limit(1)
        )
        sender = ManualPackageSender(
            OUTBOX_DIR,
            match.explanation if match is not None else "",
        )
    result = sender.send(application, job, cv_path)
    change_status(session, application, result.status, result.message)
    session.commit()
    return result


def send_email(
    session: Session,
    application: Application,
    documents: DocumentServices,
    settings: EmailSettings | None = None,
    sender: ApplicationSender | None = None,
    now: datetime | None = None,
) -> SendResult:
    """Send a dry-run or real email after checking approval and daily limits."""
    if application.status == ApplicationStatus.sent.value or _has_sent_event(session, application.id):
        raise SenderError("This application has already been sent")
    if application.status != ApplicationStatus.approved.value:
        raise SenderError("Only approved applications can be emailed")
    job, cv_path = _job_and_cv(session, application, documents)
    if not job.apply_email:
        raise SenderError("The job has no application email address")

    settings = settings or EmailSettings.from_env()
    sender = sender or EmailSender(settings)
    if not settings.dry_run:
        _check_daily_email_limit(session, now or datetime.now(timezone.utc))
    result = sender.send(application, job, cv_path)
    change_status(session, application, result.status, result.message)
    session.commit()
    return result


def _job_and_cv(session: Session, application: Application, documents: DocumentServices):
    job = session.get(Job, application.job_id)
    if job is None:
        raise SenderError("The application job was not found")
    cv_entry = next((entry for entry in documents.cv_registry.entries if entry.id == application.cv_id), None)
    if cv_entry is None:
        raise SenderError("The selected CV is not in the current CV registry")
    return job, cv_entry.file


def _check_daily_email_limit(session: Session, now: datetime) -> None:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    cutoff = now.astimezone(timezone.utc) - timedelta(hours=24)
    sent_count = session.scalar(
        select(func.count(ApplicationEvent.id)).where(
            ApplicationEvent.to_status == ApplicationStatus.sent.value,
            ApplicationEvent.created_at >= cutoff,
        )
    )
    if sent_count >= MAX_EMAILS_PER_DAY:
        next_allowed = session.scalar(
            select(func.min(ApplicationEvent.created_at)).where(
                ApplicationEvent.to_status == ApplicationStatus.sent.value,
                ApplicationEvent.created_at >= cutoff,
            )
        )
        if next_allowed is not None and next_allowed.tzinfo is None:
            next_allowed = next_allowed.replace(tzinfo=timezone.utc)
        allowed_at = next_allowed + timedelta(hours=24) if next_allowed else cutoff + timedelta(hours=24)
        raise SenderError(f"Daily email limit reached; next email is allowed at {allowed_at.isoformat()}")


def _has_sent_event(session: Session, application_id: int) -> bool:
    return session.scalar(
        select(ApplicationEvent.id)
        .where(
            ApplicationEvent.application_id == application_id,
            ApplicationEvent.to_status == ApplicationStatus.sent.value,
        )
        .limit(1)
    ) is not None