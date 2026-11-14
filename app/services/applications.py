"""Prepare applications from saved jobs and confirmed profile facts."""
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Application, ApplicationEvent, Job, JobAnalysis, Match
from app.documents.cv_selection import CvChoice, select_cv
from app.documents.facts import build_facts
from app.documents.reviewer import review_letter
from app.schemas.enums import ApplicationStatus
from app.services.runtime import DocumentServices, build_documents
from app.profile.loader import load_profile
from app.analysis.vocabulary import get_vocabulary


class JobNotFoundError(Exception):
    pass


class JobNotPreparableError(Exception):
    pass


@dataclass(frozen=True)
class PreparedApplication:
    application: Application
    cv_choice: CvChoice
    created: bool


def prepare(
    session: Session,
    job_id: int,
    documents: DocumentServices | None = None,
) -> PreparedApplication:
    job = session.scalar(
        select(Job)
        .options(selectinload(Job.analyses), selectinload(Job.matches))
        .where(Job.id == job_id)
    )
    if job is None:
        raise JobNotFoundError(f"Job {job_id} was not found")

    latest_match = session.scalar(
        select(Match).where(Match.job_id == job_id).order_by(Match.id.desc()).limit(1)
    )
    if latest_match is None or latest_match.decision not in {"queued", "needs_review"}:
        decision = latest_match.decision if latest_match is not None else "unmatched"
        raise JobNotPreparableError(f"Job cannot be prepared because its latest decision is '{decision}'")

    analysis = session.get(JobAnalysis, latest_match.analysis_id) if latest_match.analysis_id else None
    if analysis is None:
        raise JobNotPreparableError("Job cannot be prepared because its latest match has no analysis")

    application = session.scalar(select(Application).where(Application.job_id == job_id))
    if application is not None and application.status != ApplicationStatus.prepared.value:
        raise JobNotPreparableError("Application can only be refreshed while its status is 'prepared'")

    documents = documents or build_documents(load_profile(vocabulary=get_vocabulary()), get_vocabulary())
    facts = build_facts(job, analysis, documents.profile)
    cv_choice = select_cv(job, analysis, documents.cv_registry, documents.vocabulary)
    letter = documents.letter_writer.write(job, facts, documents.profile)
    issues = review_letter(letter, job, documents.profile, documents.vocabulary)
    serialized_issues = [issue.model_dump(mode="json") for issue in issues]
    was_created = application is None
    previous_status = application.status if application is not None else None

    if application is None:
        application = Application(
            job_id=job_id,
            status=ApplicationStatus.prepared.value,
        )
    application.cv_id = cv_choice.cv_id
    application.letter_text = letter
    application.review_issues = serialized_issues
    application.updated_at = datetime.now(timezone.utc)
    session.add(application)
    session.flush()
    session.add(
        ApplicationEvent(
            application_id=application.id,
            from_status=previous_status,
            to_status=ApplicationStatus.prepared.value,
            note="Application prepared" if was_created else "Prepared application refreshed",
        )
    )
    session.commit()
    return PreparedApplication(application, cv_choice, was_created)
