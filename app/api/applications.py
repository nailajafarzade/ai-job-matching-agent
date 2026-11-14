"""Read prepared applications."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db.models import Application
from app.schemas.application import ApplicationRead

router = APIRouter(prefix="/applications", tags=["applications"])


@router.get("/{application_id}", response_model=ApplicationRead, summary="Get a prepared application")
def get_application(application_id: int, session: Session = Depends(get_db)) -> ApplicationRead:
    application = session.get(Application, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return ApplicationRead.model_validate(application)
