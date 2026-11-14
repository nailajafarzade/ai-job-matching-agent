"""Fetch and normalize remote jobs from RemoteOK's public API."""
import httpx
from pydantic import ValidationError

from app.collectors.base import CollectorError, get_json
from app.collectors.contact import find_apply_email
from app.collectors.location import parse_location
from app.collectors.text import html_to_text
from app.schemas.enums import RemoteEligibility, RemoteType
from app.schemas.job import JobCreate

API_URL = "https://remoteok.com/api"


class RemoteOKCollector:
    name = "remoteok"

    def __init__(self, client: httpx.Client):
        self.client = client

    def fetch(self, search: str | None = None, limit: int = 50) -> list[JobCreate]:
        payload = get_json(self.client, API_URL)
        if not isinstance(payload, list):
            raise CollectorError("RemoteOK returned an unexpected response; expected a job list")

        jobs = []
        for item in payload[1:]:  # RemoteOK puts its legal notice first.
            if not isinstance(item, dict):
                continue
            raw_description = item.get("description")
            title = item.get("position")
            company = item.get("company")
            if not isinstance(raw_description, str) or not isinstance(title, str) or not isinstance(company, str):
                continue
            description = html_to_text(raw_description)
            if len(description.strip()) < 30:
                continue
            raw_tags = item.get("tags")
            tags = raw_tags if isinstance(raw_tags, list) else []
            searchable = " ".join(
                str(value) for value in (title, company, description, *tags)
                if value
            )
            if search and search.casefold() not in searchable.casefold():
                continue

            location = item.get("location")
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
            if len(jobs) >= limit:
                break
        return jobs
