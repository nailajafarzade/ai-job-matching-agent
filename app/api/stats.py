"""Application and match statistics."""
from collections import Counter
from typing import cast

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db.models import Application, Match
from app.schemas.application import ApplicationWeekCount, StatsRead
from app.schemas.enums import ApplicationStatus, MatchDecision

router = APIRouter(tags=["stats"])


@router.get("/stats", response_model=StatsRead, summary="Get application and match statistics")
def get_stats(session: Session = Depends(get_db)) -> StatsRead:
    status_counts = {status.value: 0 for status in ApplicationStatus}
    for status, count in session.execute(
        select(Application.status, func.count(Application.id)).group_by(Application.status)
    ):
        status_counts[status] = count

    latest_matches = (
        select(Match.job_id, func.max(Match.id).label("match_id"))
        .group_by(Match.job_id)
        .subquery()
    )
    decision_counts = {decision.value: 0 for decision in MatchDecision}
    for decision, count in session.execute(
        select(Match.decision, func.count(Match.id))
        .join(latest_matches, Match.id == latest_matches.c.match_id)
        .group_by(Match.decision)
    ):
        decision_counts[decision] = count

    average_score = session.scalar(
        select(func.avg(Match.final_score))
        .join(latest_matches, Match.id == latest_matches.c.match_id)
        .where(Match.final_score.is_not(None))
    )

    weeks = Counter()
    for created_at in session.scalars(select(Application.created_at)):
        iso_date = created_at.isocalendar()
        weeks[(iso_date.year, iso_date.week)] += 1
    applications_per_week = [
        ApplicationWeekCount(week=f"{year}-W{week:02d}", count=count)
        for (year, week), count in sorted(weeks.items())
    ]

    return StatsRead(
        applications_by_status=status_counts,
        matches_by_decision=decision_counts,
        average_final_score=float(cast(float, average_score)) if average_score is not None else None,
        applications_per_week=applications_per_week,
    )
