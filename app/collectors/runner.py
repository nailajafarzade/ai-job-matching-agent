"""Run collectors politely and pass each valid job through the pipeline."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors.base import CollectorError, CollectorRateLimitError, JobCollector
from app.config import MAX_RUNS_PER_DAY, MIN_SECONDS_BETWEEN_RUNS
from app.db.models import CollectorRun
from app.schemas.enums import MatchDecision
from app.services.pipeline import JobPipeline


@dataclass
class CollectorSummary:
    fetched: int = 0
    new: int = 0
    duplicates: int = 0
    rejected: int = 0
    needs_review: int = 0
    below_threshold: int = 0
    queued: int = 0


def run_collector(
    session: Session,
    pipeline: JobPipeline,
    collector: JobCollector,
    search: str | None = None,
    limit: int = 50,
    now: datetime | None = None,
) -> CollectorSummary:
    """Fetch, save a run record, and process jobs independently."""
    started_at = _as_utc(now or datetime.now(timezone.utc))
    _ensure_allowed(session, collector.name, started_at)

    run = CollectorRun(source=collector.name, started_at=started_at)
    session.add(run)
    session.commit()
    run_id = run.id

    try:
        jobs = collector.fetch(search=search, limit=limit)
    except Exception as error:
        _finish_run(session, run_id, error=str(error))
        if isinstance(error, CollectorError):
            raise
        raise CollectorError(f"Collector {collector.name} failed: {error}") from error

    summary = CollectorSummary(fetched=len(jobs))
    errors = []
    for job in jobs:
        try:
            result = pipeline.submit(session, job)
            if result.duplicate:
                summary.duplicates += 1
                continue
            summary.new += 1
            if result.match is not None:
                decision = result.match.decision
                if isinstance(decision, MatchDecision):
                    decision = decision.value
                if decision in {"rejected", "needs_review", "below_threshold", "queued"}:
                    setattr(summary, decision, getattr(summary, decision) + 1)
        except Exception as error:
            session.rollback()
            errors.append(str(error))

    _finish_run(session, run_id, summary, errors)
    return summary


def _ensure_allowed(session: Session, source: str, now: datetime) -> None:
    window_start = now - timedelta(hours=24)
    recent_runs = session.scalars(
        select(CollectorRun)
        .where(CollectorRun.source == source, CollectorRun.started_at >= window_start)
        .order_by(CollectorRun.started_at.desc())
    ).all()
    next_allowed = None
    if recent_runs:
        latest = _as_utc(recent_runs[0].started_at) + timedelta(seconds=MIN_SECONDS_BETWEEN_RUNS)
        next_allowed = latest
    if len(recent_runs) >= MAX_RUNS_PER_DAY:
        oldest = min(_as_utc(run.started_at) for run in recent_runs)
        daily_limit = oldest + timedelta(hours=24)
        next_allowed = max(next_allowed, daily_limit) if next_allowed else daily_limit
    if next_allowed is not None and now < next_allowed:
        raise CollectorRateLimitError(next_allowed)


def _finish_run(
    session: Session,
    run_id: int,
    summary: CollectorSummary | None = None,
    errors: list[str] | None = None,
    error: str | None = None,
) -> None:
    run = session.get(CollectorRun, run_id)
    if run is None:
        return
    run.finished_at = _as_utc(datetime.now(timezone.utc))
    if summary is not None:
        run.fetched = summary.fetched
        run.new_jobs = summary.new
        run.duplicates = summary.duplicates
    messages = [message for message in ([error] if error else []) + (errors or []) if message]
    if messages:
        run.error = "; ".join(messages)[:4000]
    session.commit()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
