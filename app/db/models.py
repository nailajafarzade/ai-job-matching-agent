"""Database tables for jobs, matching and applications.

Design rules:
- jobs holds the raw facts of a job post.
- job_analyses holds what the analyzer found (one row per analyzer version).
- matches holds the decision. It stores every part of the score, the reason,
  and the versions (profile, matcher, embedding model, weights), so any
  result can be explained and recalculated later.
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.schemas.enums import ApplicationStatus, JobStatus, MatchDecision, RemoteEligibility, RemoteType, Seniority


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(50), default="manual")
    apply_email: Mapped[str | None] = mapped_column(String(320))
    url: Mapped[str | None] = mapped_column(String(1000))
    title: Mapped[str] = mapped_column(String(300))
    company: Mapped[str] = mapped_column(String(300))
    location: Mapped[str | None] = mapped_column(String(300))
    country: Mapped[str | None] = mapped_column(String(100))
    remote_type: Mapped[str] = mapped_column(String(20), default=RemoteType.unknown.value)

    # Remote eligibility: can someone in Azerbaijan apply?
    eligible_countries: Mapped[list] = mapped_column(JSON, default=list)
    remote_work_eligibility: Mapped[str] = mapped_column(String(20), default=RemoteEligibility.unknown.value)
    location_restrictions: Mapped[str | None] = mapped_column(Text)

    description_raw: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # dedupe
    status: Mapped[str] = mapped_column(String(20), default=JobStatus.new.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    analyses: Mapped[list["JobAnalysis"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", order_by="JobAnalysis.id"
    )
    matches: Mapped[list["Match"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", order_by="Match.id"
    )
    application: Mapped["Application | None"] = relationship(
        back_populates="job", cascade="all, delete-orphan", uselist=False
    )


class JobAnalysis(Base):
    __tablename__ = "job_analyses"
    __table_args__ = (UniqueConstraint("job_id", "analyzer_version", name="uq_analysis_job_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    analyzer_version: Mapped[str] = mapped_column(String(20))
    required_skills: Mapped[list] = mapped_column(JSON, default=list)       # canonical names
    nice_to_have_skills: Mapped[list] = mapped_column(JSON, default=list)   # canonical names
    min_years: Mapped[int | None] = mapped_column(Integer)                  # None = not stated
    seniority: Mapped[str] = mapped_column(String(20), default=Seniority.unknown.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    job: Mapped[Job] = relationship(back_populates="analyses")


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (Index("ix_matches_job_created", "job_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    analysis_id: Mapped[int | None] = mapped_column(ForeignKey("job_analyses.id", ondelete="SET NULL"))

    decision: Mapped[str] = mapped_column(String(20), default=MatchDecision.rejected.value)
    reject_reasons: Mapped[list] = mapped_column(JSON, default=list)   # hard filter reasons
    review_reasons: Mapped[list] = mapped_column(JSON, default=list)   # things to check by hand

    # 0-100. All four are None when the hard filter rejected the job.
    final_score: Mapped[float | None] = mapped_column(Float)
    skill_score: Mapped[float | None] = mapped_column(Float)
    semantic_score: Mapped[float | None] = mapped_column(Float)
    title_score: Mapped[float | None] = mapped_column(Float)

    matched_skills: Mapped[list] = mapped_column(JSON, default=list)   # hands-on skills
    studied_skills: Mapped[list] = mapped_column(JSON, default=list)   # studied only (partial credit)
    missing_skills: Mapped[list] = mapped_column(JSON, default=list)   # never added to the profile
    explanation: Mapped[str] = mapped_column(Text, default="")

    # Versions: needed to recalculate old results later.
    profile_version: Mapped[int] = mapped_column(Integer)
    matcher_version: Mapped[str] = mapped_column(String(20))
    embedding_model: Mapped[str | None] = mapped_column(String(100))
    weights: Mapped[dict] = mapped_column(JSON, default=dict)          # weights used for this result
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    job: Mapped[Job] = relationship(back_populates="matches")


class CollectorRun(Base):
    __tablename__ = "collector_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(50))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    new_jobs: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    duplicates: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("job_id", name="uq_applications_job_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    cv_id: Mapped[str | None] = mapped_column(String(100))
    letter_text: Mapped[str | None] = mapped_column(Text)
    review_issues: Mapped[list] = mapped_column(JSON, default=list, server_default=text("'[]'"))
    status: Mapped[str] = mapped_column(
        String(30), default=ApplicationStatus.prepared.value, server_default=ApplicationStatus.prepared.value
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    job: Mapped[Job] = relationship(back_populates="application")
    events: Mapped[list["ApplicationEvent"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", order_by="ApplicationEvent.id"
    )


class ApplicationEvent(Base):
    __tablename__ = "application_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str] = mapped_column(String(30))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    application: Mapped[Application] = relationship(back_populates="events")
