"""Application approval, status tracking and history endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db.models import Application, ApplicationEvent
from app.schemas.application import (
    ApplicationEventRead,
    ApplicationRead,
    ApproveRequest,
    SkipRequest,
    StatusChangeRequest,
)
from app.schemas.enums import ApplicationStatus
from app.services.tracker import (
    ApprovalRefusedError,
    InvalidTransitionError,
    approve,
    change_status,
    skip,
)

router = APIRouter(prefix="/applications", tags=["applications"])


def _get_application(session: Session, application_id: int) -> Application:
    application = session.get(Application, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return application


@router.get("", response_model=list[ApplicationRead], summary="List applications")
def list_applications(
    status: ApplicationStatus | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db),
) -> list[ApplicationRead]:
    statement = select(Application)
    if status is not None:
        statement = statement.where(Application.status == status.value)
    applications = session.scalars(
        statement.order_by(Application.created_at.desc(), Application.id.desc()).offset(offset).limit(limit)
    ).all()
    return [ApplicationRead.model_validate(application) for application in applications]


@router.get("/{application_id}", response_model=ApplicationRead, summary="Get a prepared application")
def get_application(application_id: int, session: Session = Depends(get_db)) -> ApplicationRead:
    return ApplicationRead.model_validate(_get_application(session, application_id))


@router.post("/{application_id}/approve", response_model=ApplicationRead, summary="Approve an application")
def approve_application(
    application_id: int,
    request: ApproveRequest | None = None,
    session: Session = Depends(get_db),
) -> ApplicationRead:
    application = _get_application(session, application_id)
    request = request or ApproveRequest()
    try:
        approve(session, application, request.eligibility_checked, request.note)
    except (ApprovalRefusedError, InvalidTransitionError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    return ApplicationRead.model_validate(application)


@router.post("/{application_id}/skip", response_model=ApplicationRead, summary="Skip an application")
def skip_application(
    application_id: int,
    request: SkipRequest | None = None,
    session: Session = Depends(get_db),
) -> ApplicationRead:
    application = _get_application(session, application_id)
    try:
        skip(session, application, request.note if request else None)
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    return ApplicationRead.model_validate(application)


@router.post("/{application_id}/status", response_model=ApplicationRead, summary="Change application status")
def update_application_status(
    application_id: int,
    request: StatusChangeRequest,
    session: Session = Depends(get_db),
) -> ApplicationRead:
    application = _get_application(session, application_id)
    try:
        change_status(session, application, request.status, request.note)
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    return ApplicationRead.model_validate(application)


@router.get(
    "/{application_id}/events",
    response_model=list[ApplicationEventRead],
    summary="List application status history",
)
def list_application_events(
    application_id: int,
    session: Session = Depends(get_db),
) -> list[ApplicationEventRead]:
    application = _get_application(session, application_id)
    events = session.scalars(
        select(ApplicationEvent)
        .where(ApplicationEvent.application_id == application.id)
        .order_by(ApplicationEvent.id.asc())
    ).all()
    return [ApplicationEventRead.model_validate(event) for event in events]
