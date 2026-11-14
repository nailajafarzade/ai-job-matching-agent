"""Run the full application flow locally without network access or model downloads."""
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors.runner import run_collector
from app.config import OUTBOX_DIR, PROFILE_PATH
from app.db.models import Job, Match
from app.db.session import Base, make_engine
from app.schemas.enums import RemoteEligibility, RemoteType
from app.schemas.job import JobCreate
from app.senders.manual import ManualPackageSender
from app.services.applications import prepare
from app.services.runtime import build_documents, build_pipeline
from app.services.sending import prepare_package
from app.services.tracker import approve
from tests.fakes import HashingEmbedder


class DemoCollector:
    name = "demo"

    def fetch(self, search: str | None = None, limit: int = 50) -> list[JobCreate]:
        """Return one fixed job post without making a network request."""
        return [
            JobCreate(
                source=self.name,
                title="Junior Java Backend Developer",
                company="Example Demo Company",
                url="https://example.test/jobs/demo",
                apply_email="apply@example.test",
                description=(
                    "We are looking for a junior Java backend developer. Required skills include Java, "
                    "Spring Boot, PostgreSQL and REST API. Build backend services with our team."
                ),
                remote_type=RemoteType.remote,
                remote_work_eligibility=RemoteEligibility.eligible,
                eligible_countries=["Azerbaijan"],
            )
        ][:limit]


def main(database_url: str = "sqlite:///:memory:", outbox_dir: Path = OUTBOX_DIR) -> int:
    engine = make_engine(database_url)
    try:
        Base.metadata.create_all(engine)
        with Session(engine, autoflush=False, expire_on_commit=False) as session:
            pipeline = build_pipeline(PROFILE_PATH, HashingEmbedder(), min_score=0)
            documents = build_documents(pipeline.matcher.profile, pipeline.matcher.vocabulary)

            print("1. Collecting one mocked job...")
            summary = run_collector(session, pipeline, DemoCollector(), limit=1)
            print(f"   Collector: new={summary.new}, duplicates={summary.duplicates}")

            job = session.scalar(select(Job).where(Job.company == "Example Demo Company"))
            if job is None:
                raise RuntimeError("The demo collector did not save its job")
            match = session.scalar(
                select(Match).where(Match.job_id == job.id).order_by(Match.id.desc()).limit(1)
            )
            print(f"2. Analyzed and matched: decision={match.decision}, score={match.final_score}")

            print("3. Preparing the profile-backed CV choice and letter...")
            prepared = prepare(session, job.id, documents)
            application = prepared.application
            print(f"   CV: {prepared.cv_choice.cv_id} ({prepared.cv_choice.reason})")
            print(f"   Reviewer issues: {application.review_issues}")

            print("4. Approving the application for manual submission...")
            approve(session, application)
            session.commit()
            print(f"   Status: {application.status}")

            print("5. Creating a local manual application package...")
            result = prepare_package(
                session,
                application,
                documents,
                ManualPackageSender(outbox_dir, match.explanation),
            )
            print(f"   Status: {application.status}; package: {result.path}")
            print(f"   {result.message}")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())