"""Dashboard pages and form actions."""
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_db
from app.api.stats import get_stats
from app.db.models import Application, Job, Match
from app.documents.cv_selection import CvChoice, select_cv
from app.schemas.enums import ApplicationStatus, MatchDecision
from app.services.applications import JobNotFoundError, JobNotPreparableError, prepare
from app.senders.base import SenderError
from app.senders.settings import EmailSettings
from app.services.sending import prepare_package, send_email
from app.services.tracker import (
    ALLOWED,
    ApprovalRefusedError,
    InvalidTransitionError,
    approve,
    change_status,
    skip,
)

router = APIRouter(prefix="/ui", tags=["dashboard"])
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.autoescape = True


def _job_query(session: Session, job_id: int) -> Job | None:
    return session.scalar(
        select(Job)
        .options(
            selectinload(Job.analyses),
            selectinload(Job.matches),
            selectinload(Job.application).selectinload(Application.events),
        )
        .where(Job.id == job_id)
    )


def _redirect_to_job(job_id: int, message: str | None = None, error: str | None = None) -> RedirectResponse:
    query = urlencode({key: value for key, value in {"message": message, "error": error}.items() if value})
    suffix = f"?{query}" if query else ""
    return RedirectResponse(f"/ui/jobs/{job_id}{suffix}", status_code=303)


def _get_application(session: Session, application_id: int) -> Application:
    application = session.get(Application, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return application


def _cv_choice(request: Request, job: Job, analysis) -> CvChoice | None:
    if analysis is None:
        return None
    documents = request.app.state.documents
    return select_cv(job, analysis, documents.cv_registry, documents.vocabulary)


@router.get("", response_class=HTMLResponse, summary="Job dashboard")
def dashboard(
    request: Request,
    decision: MatchDecision | None = None,
    status: ApplicationStatus | None = None,
    session: Session = Depends(get_db),
) -> HTMLResponse:
    latest_match_id = (
        select(func.max(Match.id))
        .where(Match.job_id == Job.id)
        .correlate(Job)
        .scalar_subquery()
    )
    statement = (
        select(Job)
        .outerjoin(Match, Match.id == latest_match_id)
        .outerjoin(Application, Application.job_id == Job.id)
        .options(selectinload(Job.analyses), selectinload(Job.matches), selectinload(Job.application))
    )
    if decision is not None:
        statement = statement.where(Match.decision == decision.value)
    if status is not None:
        statement = statement.where(Application.status == status.value)
    jobs = session.scalars(
        statement.order_by(Match.final_score.desc().nullslast(), Job.created_at.desc(), Job.id.desc())
    ).all()
    rows = [
        {
            "job": job,
            "match": job.matches[-1] if job.matches else None,
            "application": job.application,
        }
        for job in jobs
    ]
    return templates.TemplateResponse(
        request=request,
        name="jobs.html.j2",
        context={
            "rows": rows,
            "decision": decision.value if decision else "",
            "status": status.value if status else "",
            "decisions": list(MatchDecision),
            "statuses": list(ApplicationStatus),
        },
    )


@router.get("/jobs/{job_id}", response_class=HTMLResponse, summary="Job and application details")
def job_detail(request: Request, job_id: int, session: Session = Depends(get_db)) -> HTMLResponse:
    job = _job_query(session, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    match = job.matches[-1] if job.matches else None
    analysis = job.analyses[-1] if job.analyses else None
    application = job.application
    choice = _cv_choice(request, job, analysis) if application else None
    cv_entry = next(
        (entry for entry in request.app.state.documents.cv_registry.entries if application and entry.id == application.cv_id),
        None,
    )
    if application is None or choice is None:
        cv_reason = None
    elif choice.cv_id == application.cv_id:
        cv_reason = choice.reason
    else:
        cv_reason = f"The stored CV is {application.cv_id}; the current registry would choose {choice.cv_id}."
    allowed_statuses = sorted(ALLOWED.get(application.status, set())) if application else []
    return templates.TemplateResponse(
        request=request,
        name="job_detail.html.j2",
        context={
            "job": job,
            "match": match,
            "analysis": analysis,
            "application": application,
            "cv_entry": cv_entry,
            "cv_reason": cv_reason,
            "allowed_statuses": allowed_statuses,
            "message": request.query_params.get("message"),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/stats", response_class=HTMLResponse, summary="Dashboard statistics")
def dashboard_stats(request: Request, session: Session = Depends(get_db)) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="stats.html.j2",
        context={"stats": get_stats(session)},
    )


@router.get("/applications/{application_id}/email", response_class=HTMLResponse)
def confirm_email(request: Request, application_id: int, session: Session = Depends(get_db)) -> HTMLResponse:
    application = _get_application(session, application_id)
    if application.status != ApplicationStatus.approved.value:
        raise HTTPException(status_code=409, detail="Only approved applications can be emailed")
    job = session.get(Job, application.job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.apply_email:
        raise HTTPException(status_code=409, detail="The job has no application email address")
    settings = EmailSettings.from_env()
    cv_entry = next(
        (entry for entry in request.app.state.documents.cv_registry.entries if entry.id == application.cv_id),
        None,
    )
    return templates.TemplateResponse(
        request=request,
        name="email_confirmation.html.j2",
        context={
            "application": application,
            "job": job,
            "mode": "DRY RUN" if settings.dry_run else "REAL",
            "mode_value": "dry_run" if settings.dry_run else "real",
            "cv_entry": cv_entry,
        },
    )


@router.post("/applications/{application_id}/package")
def prepare_application_package(
    request: Request,
    application_id: int,
    session: Session = Depends(get_db),
) -> RedirectResponse:
    application = _get_application(session, application_id)
    try:
        result = prepare_package(session, application, request.app.state.documents)
    except SenderError as exc:
        session.rollback()
        return _redirect_to_job(application.job_id, error=str(exc))
    return _redirect_to_job(application.job_id, message=result.message)


@router.post("/applications/{application_id}/email")
def send_email_application(
    request: Request,
    application_id: int,
    confirmed: bool = Form(default=False),
    confirmed_mode: str = Form(),
    session: Session = Depends(get_db),
) -> RedirectResponse:
    application = _get_application(session, application_id)
    try:
        settings = EmailSettings.from_env()
        current_mode = "dry_run" if settings.dry_run else "real"
        if not confirmed:
            raise SenderError("Check the confirmation box before continuing")
        if confirmed_mode != current_mode:
            raise SenderError("Email mode changed; review the confirmation page again")
        result = send_email(session, application, request.app.state.documents, settings=settings)
    except (SenderError, ValueError) as exc:
        session.rollback()
        return _redirect_to_job(application.job_id, error=str(exc))
    return _redirect_to_job(application.job_id, message=result.message)


@router.post("/jobs/{job_id}/prepare")
def prepare_application(request: Request, job_id: int, session: Session = Depends(get_db)) -> RedirectResponse:
    try:
        prepare(session, job_id, request.app.state.documents)
    except (JobNotFoundError, JobNotPreparableError) as exc:
        return _redirect_to_job(job_id, error=str(exc))
    return _redirect_to_job(job_id, message="Application prepared.")


@router.post("/applications/{application_id}/approve")
def approve_application(
    application_id: int,
    eligibility_checked: bool = Form(default=False),
    note: str | None = Form(default=None),
    session: Session = Depends(get_db),
) -> RedirectResponse:
    application = _get_application(session, application_id)
    try:
        approve(session, application, eligibility_checked, note)
        session.commit()
    except (ApprovalRefusedError, InvalidTransitionError) as exc:
        session.rollback()
        return _redirect_to_job(application.job_id, error=f"Approval refused: {exc}")
    return _redirect_to_job(application.job_id, message="Application approved.")


@router.post("/applications/{application_id}/skip")
def skip_application(
    application_id: int,
    note: str | None = Form(default=None),
    session: Session = Depends(get_db),
) -> RedirectResponse:
    application = _get_application(session, application_id)
    try:
        skip(session, application, note)
        session.commit()
    except InvalidTransitionError as exc:
        session.rollback()
        return _redirect_to_job(application.job_id, error=str(exc))
    return _redirect_to_job(application.job_id, message="Application skipped.")


@router.post("/applications/{application_id}/status")
def update_status(
    application_id: int,
    status: str = Form(),
    note: str | None = Form(default=None),
    session: Session = Depends(get_db),
) -> RedirectResponse:
    application = _get_application(session, application_id)
    try:
        target = ApplicationStatus(status)
        change_status(session, application, target, note)
        session.commit()
    except (ValueError, InvalidTransitionError) as exc:
        session.rollback()
        return _redirect_to_job(application.job_id, error=str(exc))
    return _redirect_to_job(application.job_id, message=f"Status changed to {target.value}.")
