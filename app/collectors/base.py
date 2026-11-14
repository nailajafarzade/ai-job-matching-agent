"""Shared collector interface and HTTP client settings."""
from typing import Protocol

import httpx

from app.schemas.job import JobCreate

USER_AGENT = "job-agent personal project"
REQUEST_TIMEOUT = 20


class CollectorError(RuntimeError):
    """A collector could not complete its request or parse the response."""


class CollectorRateLimitError(CollectorError):
    """A source cannot be requested again until the given time."""

    def __init__(self, next_allowed_at):
        self.next_allowed_at = next_allowed_at
        super().__init__(f"Next run is allowed at {next_allowed_at.isoformat()}")


class JobCollector(Protocol):
    name: str

    def fetch(self, search: str | None = None, limit: int = 50) -> list[JobCreate]:
        """Fetch jobs and convert them to the shared input schema."""


def get_json(client: httpx.Client, url: str, params: dict | None = None):
    """Request JSON with the shared timeout and generic user agent."""
    try:
        response = client.get(
            url,
            params=params,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise CollectorError(f"Could not fetch collector data: {error}") from error
