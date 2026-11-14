"""Run public job collectors and inspect their run history."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.collectors.base import CollectorError, CollectorRateLimitError, JobCollector
from app.collectors.runner import run_collector
from app.db.models import CollectorRun
from app.schemas.collector import CollectorRunRead, CollectorRunRequest, CollectorSummaryRead
from app.services.pipeline import JobPipeline

router = APIRouter(prefix="/collectors", tags=["collectors"])


def _get_pipeline(request: Request):
    return request.app.state.pipeline


def _get_collectors(request: Request) -> dict[str, JobCollector]:
    return request.app.state.collectors


@router.post("/{source}/run", response_model=CollectorSummaryRead, summary="Run one job collector")
def run_source(
    source: str,
    data: CollectorRunRequest,
    session: Session = Depends(get_db),
    pipeline: JobPipeline = Depends(_get_pipeline),
    collectors: dict[str, JobCollector] = Depends(_get_collectors),
) -> CollectorSummaryRead:
    collector = collectors.get(source)
    if collector is None:
        raise HTTPException(status_code=404, detail=f"Unknown collector source: {source}")
    try:
        summary = run_collector(session, pipeline, collector, data.search, data.limit)
    except CollectorRateLimitError as error:
        raise HTTPException(status_code=429, detail=str(error)) from error
    except CollectorError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return CollectorSummaryRead(**summary.__dict__)


@router.get("/runs", response_model=list[CollectorRunRead], summary="List recent collector runs")
def list_runs(
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_db),
) -> list[CollectorRunRead]:
    runs = session.scalars(
        select(CollectorRun).order_by(CollectorRun.started_at.desc(), CollectorRun.id.desc()).limit(limit)
    ).all()
    return [CollectorRunRead.model_validate(run) for run in runs]
