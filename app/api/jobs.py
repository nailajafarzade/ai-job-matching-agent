"""Job submission, listing and rematch endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_db, get_pipeline
from app.db.models import Job, Match
from app.schemas.analysis import JobAnalysisRead
from app.schemas.enums import MatchDecision
from app.schemas.job import JobCreate, JobRead
from app.schemas.match import MatchRead
from app.schemas.responses import JobResult
from app.services.pipeline import JobPipeline, PipelineResult

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _job_result(result: PipelineResult, duplicate: bool | None = None) -> JobResult:
    return JobResult(
        duplicate=result.duplicate if duplicate is None else duplicate,
        job=JobRead.model_validate(result.job),
        analysis=JobAnalysisRead.model_validate(result.analysis) if result.analysis else None,
        match=MatchRead.model_validate(result.match) if result.match else None,
    )


def _loaded_job(session: Session, job_id: int) -> Job | None:
    return session.scalar(
        select(Job)
        .options(selectinload(Job.analyses), selectinload(Job.matches))
        .where(Job.id == job_id)
    )


@router.post(
    "",
    response_model=JobResult,
    status_code=status.HTTP_201_CREATED,
    summary="Submit and match a job post",
)
def submit_job(
    data: JobCreate,
    response: Response,
    session: Session = Depends(get_db),
    pipeline: JobPipeline = Depends(get_pipeline),
) -> JobResult:
    result = pipeline.submit(session, data)
    if result.duplicate:
        response.status_code = status.HTTP_200_OK
    return _job_result(result)


@router.get("", response_model=list[JobResult], summary="List and filter saved jobs")
def list_jobs(
    decision: MatchDecision | None = None,
    min_score: float | None = Query(default=None, ge=0, le=100),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db),
) -> list[JobResult]:
    latest_match_id = (
        select(func.max(Match.id))
        .where(Match.job_id == Job.id)
        .correlate(Job)
        .scalar_subquery()
    )
    statement = select(Job).options(selectinload(Job.analyses), selectinload(Job.matches))
    if decision is not None or min_score is not None:
        statement = statement.join(Match, Match.id == latest_match_id)
        if decision is not None:
            statement = statement.where(Match.decision == decision.value)
        if min_score is not None:
            statement = statement.where(Match.final_score >= min_score)
    jobs = session.scalars(
        statement.order_by(Job.created_at.desc(), Job.id.desc()).offset(offset).limit(limit)
    ).all()
    return [
        JobResult(
            duplicate=False,
            job=JobRead.model_validate(job),
            analysis=JobAnalysisRead.model_validate(job.analyses[-1]) if job.analyses else None,
            match=MatchRead.model_validate(job.matches[-1]) if job.matches else None,
        )
        for job in jobs
    ]


@router.get("/{job_id}", response_model=JobResult, summary="Get a job and its latest result")
def get_job(job_id: int, session: Session = Depends(get_db)) -> JobResult:
    job = _loaded_job(session, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResult(
        duplicate=False,
        job=JobRead.model_validate(job),
        analysis=JobAnalysisRead.model_validate(job.analyses[-1]) if job.analyses else None,
        match=MatchRead.model_validate(job.matches[-1]) if job.matches else None,
    )


@router.get("/{job_id}/matches", response_model=list[MatchRead], summary="List a job's match history")
def list_job_matches(job_id: int, session: Session = Depends(get_db)) -> list[MatchRead]:
    if session.get(Job, job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found")
    matches = session.scalars(
        select(Match).where(Match.job_id == job_id).order_by(Match.id.asc())
    ).all()
    return [MatchRead.model_validate(match) for match in matches]


@router.post(
    "/{job_id}/rematch",
    response_model=JobResult,
    summary="Create a new match with the current profile",
)
def rematch_job(
    job_id: int,
    session: Session = Depends(get_db),
    pipeline: JobPipeline = Depends(get_pipeline),
) -> JobResult:
    result = pipeline.rematch(session, job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_result(result, duplicate=False)
