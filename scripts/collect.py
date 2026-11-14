"""Run one public job collector from the command line."""
import argparse
import sys
from collections.abc import Callable

import httpx
from sqlalchemy.orm import sessionmaker

from app.collectors.base import CollectorError, CollectorRateLimitError
from app.collectors.runner import run_collector
from app.collectors.remoteok import RemoteOKCollector
from app.collectors.remotive import RemotiveCollector
from app.config import DATABASE_URL, PROFILE_PATH
from app.db.session import init_db, make_engine
from app.matching.embeddings import Embedder, get_embedder
from app.services.runtime import build_pipeline


def main(
    argv: list[str] | None = None,
    *,
    database_url: str = DATABASE_URL,
    client_factory: Callable[[], httpx.Client] | None = None,
    embedder_factory: Callable[[], Embedder] | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Collect public remote jobs and score them")
    parser.add_argument("--source", required=True, choices=("remotive", "remoteok"))
    parser.add_argument("--search")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args(argv)
    if args.limit < 1:
        parser.error("--limit must be at least 1")

    engine = make_engine(database_url)
    try:
        init_db(engine)
        session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        client_factory = client_factory or httpx.Client
        embedder_factory = embedder_factory or get_embedder
        with client_factory() as client, session_factory() as session:
            collector = RemotiveCollector(client) if args.source == "remotive" else RemoteOKCollector(client)
            pipeline = build_pipeline(PROFILE_PATH, embedder_factory())
            summary = run_collector(session, pipeline, collector, args.search, args.limit)
        print(
            "Collector summary: "
            f"fetched={summary.fetched}, new={summary.new}, duplicates={summary.duplicates}, "
            f"rejected={summary.rejected}, needs_review={summary.needs_review}, "
            f"below_threshold={summary.below_threshold}, queued={summary.queued}"
        )
        return 0
    except (CollectorError, CollectorRateLimitError) as error:
        print(str(error), file=sys.stderr)
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
