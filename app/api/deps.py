"""Shared FastAPI dependencies."""
from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session

from app.services.pipeline import JobPipeline
from app.services.runtime import DocumentServices


def get_db(request: Request) -> Iterator[Session]:
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def get_pipeline(request: Request) -> JobPipeline:
    return request.app.state.pipeline


def get_documents(request: Request) -> DocumentServices:
    return request.app.state.documents
