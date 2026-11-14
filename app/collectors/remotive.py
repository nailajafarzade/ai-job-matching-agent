"""Fetch and normalize remote jobs from Remotive's public API."""
import httpx
from pydantic import ValidationError

from app.collectors.base import CollectorError, get_json
from app.collectors.contact import find_apply_email
from app.collectors.location import parse_location
from app.collectors.text import html_to_text
from app.schemas.enums import RemoteEligibility, RemoteType
from app.schemas.job import JobCreate

API_URL = "https://remotive.com/api/remote-jobs"


class RemotiveCollector:
    name = "remotive"

    def __init__(self, client: httpx.Client):
        self.client = client

    def fetch(self, search: str | None = None, limit: int = 50) -> list[JobCreate]:
        params: dict[str, int | str] = {"limit": limit}
        if search:
            params["search"] = search
        payload = get_json(self.client, API_URL, params)
        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            raise CollectorError("Remotive returned an unexpected response; expected a jobs list")

        jobs = []
        for item in payload["jobs"][:limit]:
            if not isinstance(item, dict):
                continue
            raw_description = item.get("description")
            title = item.get("title")
            company = item.get("company_name")
            if not isinstance(raw_description, str) or not isinstance(title, str) or not isinstance(company, str):
                continue
            description = html_to_text(raw_description)
            if len(description.strip()) < 30:
                continue
            location = item.get("candidate_required_location")
            countries, certain = parse_location(location)
            try:
                jobs.append(
                    JobCreate(
                        source=self.name,
                        url=item.get("url"),
                        title=title,
                        company=company,
                        description=description,
                        location=location or None,
                        remote_type=RemoteType.remote,
                        eligible_countries=countries if certain else [],
                        remote_work_eligibility=RemoteEligibility.unknown,
                        location_restrictions=location or None,
                        apply_email=find_apply_email(description),
                    )
                )
            except ValidationError:
                continue
        return jobs
