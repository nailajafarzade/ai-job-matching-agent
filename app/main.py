"""FastAPI application for manual job intake and matching."""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from sqlalchemy.orm import sessionmaker

from app.api import jobs, profile
from app.config import DATABASE_URL, PROFILE_PATH
from app.db.session import init_db, make_engine
from app.matching.embeddings import Embedder, get_embedder
from app.services.runtime import build_pipeline


def create_app(
    embedder: Embedder | None = None,
    database_url: str = DATABASE_URL,
    profile_path: Path = PROFILE_PATH,
    min_score: float | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(runtime_app: FastAPI) -> AsyncIterator[None]:
        engine = make_engine(database_url)
        try:
            init_db(engine)
            runtime_app.state.engine = engine
            runtime_app.state.session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
            runtime_app.state.embedder = embedder if embedder is not None else get_embedder()
            runtime_app.state.profile_path = profile_path
            runtime_app.state.min_score = min_score
            runtime_app.state.pipeline = build_pipeline(profile_path, runtime_app.state.embedder, min_score)
            yield
        finally:
            engine.dispose()

    application = FastAPI(title="Job Agent", lifespan=lifespan)
    application.include_router(jobs.router)
    application.include_router(profile.router)

    @application.get("/health", summary="Check API and matching runtime health")
    def health(request: Request) -> dict[str, int | str]:
        pipeline = request.app.state.pipeline
        return {
            "status": "ok",
            "embedding_model": pipeline.matcher.embedder.name,
            "profile_version": pipeline.matcher.profile.version,
        }

    return application


app = create_app()
