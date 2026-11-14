import json
from pathlib import Path

import httpx

from app.analysis.analyzer import get_analyzer
from app.collectors.remoteok import RemoteOKCollector
from app.collectors.remotive import RemotiveCollector

FIXTURES = Path(__file__).parent / "collectors" / "fixtures"


def fixture_transport(file_name):
    payload = json.loads((FIXTURES / file_name).read_text(encoding="utf-8"))

    def handler(request):
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handler)


def test_remotive_converts_jobs_and_skips_short_description():
    requests = []

    def handler(request):
        requests.append(request)
        payload = json.loads((FIXTURES / "remotive.json").read_text(encoding="utf-8"))
        return httpx.Response(200, json=payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        jobs = RemotiveCollector(client).fetch(search="java", limit=10)

    assert len(jobs) == 3
    assert jobs[0].source == "remotive"
    assert jobs[0].url == "https://remotive.com/remote-jobs/software-dev/java-backend-one"
    assert jobs[0].remote_type.value == "remote"
    assert jobs[0].eligible_countries == ["Worldwide"]
    assert jobs[0].location_restrictions == "Worldwide"
    assert jobs[0].apply_email == "apply@example.com"
    assert "Requirements:\n- Java\n- Spring Boot" in jobs[0].description
    assert requests[0].url.params["search"] == "java"
    assert requests[0].url.params["limit"] == "10"
    assert requests[0].headers["user-agent"] == "job-agent personal project"


def test_remoteok_skips_legal_notice_and_short_description():
    with httpx.Client(transport=fixture_transport("remoteok.json")) as client:
        jobs = RemoteOKCollector(client).fetch(limit=10)

    assert len(jobs) == 3
    assert all(job.company != "RemoteOK" for job in jobs)
    assert jobs[0].source == "remoteok"
    assert jobs[0].title == "Junior Java Backend Developer"
    assert jobs[0].eligible_countries == ["USA"]
    assert jobs[0].apply_email == "careers@example.org"
    assert jobs[1].eligible_countries == []
    assert jobs[1].location_restrictions == "UTC-5 to UTC+1"


def test_remoteok_search_filters_locally_and_obeys_limit():
    with httpx.Client(transport=fixture_transport("remoteok.json")) as client:
        jobs = RemoteOKCollector(client).fetch(search="java", limit=1)

    assert len(jobs) == 1
    assert jobs[0].title == "Junior Java Backend Developer"


def test_collected_html_list_is_analyzed_as_required_skills():
    with httpx.Client(transport=fixture_transport("remotive.json")) as client:
        job = RemotiveCollector(client).fetch(limit=1)[0]

    result = get_analyzer().analyze(job.title, job.description)
    assert "Java" in result.required_skills
    assert "Spring Boot" in result.required_skills
