"""Run job intake, analysis and matching, and save the results."""
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.analysis.analyzer import JobAnalyzer
from app.config import ANALYZER_VERSION
from app.db.models import Job, JobAnalysis, Match
from app.intake.hashing import compute_content_hash
from app.matching.scorer import Matcher
from app.matching.types import JobFacts
from app.schemas.analysis import AnalysisResult
from app.schemas.enums import JobStatus, RemoteEligibility, RemoteType, Seniority
from app.schemas.job import JobCreate


@dataclass
class PipelineResult:
    job: Job
    analysis: JobAnalysis | None
    match: Match | None
    duplicate: bool


class JobPipeline:
    def __init__(self, analyzer: JobAnalyzer, matcher: Matcher):
        self.analyzer = analyzer
        self.matcher = matcher

    def submit(self, session: Session, data: JobCreate) -> PipelineResult:
        content_hash = compute_content_hash(data.company, data.title, data.description)
        existing = self._find_job(session, content_hash)
        if existing:
            return self._existing_result(existing)

        job = Job(
            source="manual",
            url=data.url,
            title=data.title,
            company=data.company,
            location=data.location,
            country=data.country,
            remote_type=data.remote_type.value,
            eligible_countries=data.eligible_countries,
            remote_work_eligibility=data.remote_work_eligibility.value,
            location_restrictions=data.location_restrictions,
            description_raw=data.description,
            content_hash=content_hash,
            status=JobStatus.new.value,
        )
        session.add(job)
        try:
            session.flush()
            analysis = self._analyze(job)
            session.add(analysis)
            job.status = JobStatus.analyzed.value
            session.flush()
            match = self.matcher.match(self._job_facts(job), self._analysis_result(analysis))
            saved_match = match.to_orm(job.id, analysis.id)
            session.add(saved_match)
            job.status = JobStatus.matched.value
            session.commit()
        except IntegrityError:
            session.rollback()
            existing = self._find_job(session, content_hash)
            if existing is None:
                raise
            return self._existing_result(existing)

        return PipelineResult(job, analysis, saved_match, False)

    def rematch(self, session: Session, job_id: int) -> PipelineResult | None:
        job = session.get(Job, job_id)
        if job is None:
            return None

        analysis = session.scalar(
            select(JobAnalysis)
            .where(JobAnalysis.job_id == job.id, JobAnalysis.analyzer_version == ANALYZER_VERSION)
            .order_by(JobAnalysis.id.desc())
        )
        if analysis is None:
            analysis = self._analyze(job)
            session.add(analysis)
            job.status = JobStatus.analyzed.value
            session.flush()

        result = self.matcher.match(self._job_facts(job), self._analysis_result(analysis))
        match = result.to_orm(job.id, analysis.id)
        session.add(match)
        job.status = JobStatus.matched.value
        session.commit()
        return PipelineResult(job, analysis, match, False)

    def _analyze(self, job: Job) -> JobAnalysis:
        result = self.analyzer.analyze(job.title, job.description_raw)
        return JobAnalysis(
            job_id=job.id,
            analyzer_version=ANALYZER_VERSION,
            **result.model_dump(mode="json"),
        )

    @staticmethod
    def _analysis_result(analysis: JobAnalysis) -> AnalysisResult:
        return AnalysisResult(
            required_skills=analysis.required_skills,
            nice_to_have_skills=analysis.nice_to_have_skills,
            min_years=analysis.min_years,
            seniority=Seniority(analysis.seniority),
        )

    @staticmethod
    def _job_facts(job: Job) -> JobFacts:
        return JobFacts(
            title=job.title,
            description=job.description_raw,
            country=job.country,
            location=job.location,
            remote_type=RemoteType(job.remote_type),
            eligible_countries=job.eligible_countries,
            remote_work_eligibility=RemoteEligibility(job.remote_work_eligibility),
            location_restrictions=job.location_restrictions,
        )

    @staticmethod
    def _find_job(session: Session, content_hash: str) -> Job | None:
        return session.scalar(
            select(Job)
            .options(selectinload(Job.analyses), selectinload(Job.matches))
            .where(Job.content_hash == content_hash)
        )

    @staticmethod
    def _existing_result(job: Job) -> PipelineResult:
        return PipelineResult(
            job=job,
            analysis=job.analyses[-1] if job.analyses else None,
            match=job.matches[-1] if job.matches else None,
            duplicate=True,
        )
