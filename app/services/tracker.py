"""Application status transitions and approval checks."""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Application, ApplicationEvent, Match
from app.schemas.enums import ApplicationStatus

ALLOWED = {
    ApplicationStatus.prepared.value: {
        ApplicationStatus.approved.value,
        ApplicationStatus.skipped.value,
    },
    ApplicationStatus.approved.value: {
        ApplicationStatus.package_ready.value,
        ApplicationStatus.sent.value,
        ApplicationStatus.skipped.value,
        ApplicationStatus.prepared.value,
    },
    ApplicationStatus.package_ready.value: {
        ApplicationStatus.sent.value,
        ApplicationStatus.skipped.value,
    },
    ApplicationStatus.sent.value: {
        ApplicationStatus.replied.value,
        ApplicationStatus.interview.value,
        ApplicationStatus.rejected.value,
        ApplicationStatus.withdrawn.value,
    },
    ApplicationStatus.replied.value: {
        ApplicationStatus.interview.value,
        ApplicationStatus.rejected.value,
        ApplicationStatus.withdrawn.value,
    },
    ApplicationStatus.interview.value: {
        ApplicationStatus.rejected.value,
        ApplicationStatus.withdrawn.value,
    },
    ApplicationStatus.skipped.value: {ApplicationStatus.prepared.value},
    ApplicationStatus.rejected.value: set(),
    ApplicationStatus.withdrawn.value: set(),
}


class InvalidTransitionError(Exception):
    """The requested status is not allowed from the current status."""


class ApprovalRefusedError(Exception):
    """The application does not meet the approval requirements."""


def change_status(
    session: Session,
    application: Application,
    new_status: str | ApplicationStatus,
    note: str | None = None,
) -> Application:
    """Change an application status and record the transition."""
    target_status = new_status.value if isinstance(new_status, ApplicationStatus) else new_status
    allowed = ALLOWED.get(application.status, set())
    if target_status not in allowed:
        raise InvalidTransitionError(
            f"Cannot change application from '{application.status}' to '{target_status}'"
        )

    previous_status = application.status
    application.status = target_status
    if target_status == ApplicationStatus.sent.value:
        application.sent_at = datetime.now(timezone.utc)
    session.add(
        ApplicationEvent(
            application_id=application.id,
            from_status=previous_status,
            to_status=target_status,
            note=note,
        )
    )
    session.flush()
    return application


def approve(
    session: Session,
    application: Application,
    eligibility_checked: bool = False,
    note: str | None = None,
) -> Application:
    """Approve an application only after all required checks pass."""
    reasons = []
    if any(issue.get("level") == "error" for issue in application.review_issues if isinstance(issue, dict)):
        reasons.append("the letter review contains errors")

    latest_match = session.scalar(
        select(Match).where(Match.job_id == application.job_id).order_by(Match.id.desc()).limit(1)
    )
    if latest_match is not None and latest_match.decision == "needs_review" and not eligibility_checked:
        reasons.append("eligibility_checked=true is required for a needs_review job")
    if not application.letter_text or not application.letter_text.strip():
        reasons.append("the application has no letter")
    if not application.cv_id or not application.cv_id.strip():
        reasons.append("the application has no CV")

    if reasons:
        raise ApprovalRefusedError("Approval refused: " + "; ".join(reasons))
    return change_status(session, application, ApplicationStatus.approved, note)


def skip(session: Session, application: Application, note: str | None = None) -> Application:
    """Mark an application as skipped."""
    return change_status(session, application, ApplicationStatus.skipped, note)
