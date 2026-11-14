from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas.enums import RemoteType
from app.schemas.job import JobCreate
from tests.fakes import HashingEmbedder

PROFILE = Path(__file__).parent.parent / "data" / "profile.yaml"


class TestCollector:
    __test__ = False

    name = "test-source"

    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def fetch(self, search=None, limit=50):
        self.calls.append((search, limit))
        if self.error:
            raise self.error
        return [
            JobCreate(
                source=self.name,
                title="Junior Java Backend Developer",
                company="API Collector Example",
                description=(
                    "We need a junior Java backend developer. Requirements include Java, Spring Boot, "
                    "PostgreSQL and REST API. Build backend services with the team."
                ),
                remote_type=RemoteType.remote,
                eligible_countries=["Worldwide"],
            )
        ][:limit]


def make_client(collectors):
    application = create_app(
        embedder=HashingEmbedder(),
        database_url="sqlite:///:memory:",
        profile_path=PROFILE,
        min_score=0,
        collectors=collectors,
    )
    return TestClient(application)


def test_collector_api_runs_source_and_lists_run_history():
    collector = TestCollector()
    with make_client({collector.name: collector}) as client:
        response = client.post(
            "/collectors/test-source/run",
            json={"search": "java", "limit": 4},
        )
        runs_response = client.get("/collectors/runs")

    assert response.status_code == 200
    assert response.json()["fetched"] == 1
    assert response.json()["new"] == 1
    assert collector.calls == [("java", 4)]
    assert runs_response.status_code == 200
    assert runs_response.json()[0]["source"] == "test-source"
    assert runs_response.json()[0]["new_jobs"] == 1


def test_collector_api_returns_404_for_unknown_source():
    with make_client({}) as client:
        response = client.post("/collectors/unknown/run", json={})

    assert response.status_code == 404
    assert "Unknown collector source" in response.json()["detail"]


def test_collector_api_returns_429_for_rate_limited_source():
    collector = TestCollector()
    with make_client({collector.name: collector}) as client:
        first = client.post("/collectors/test-source/run", json={})
        second = client.post("/collectors/test-source/run", json={})

    assert first.status_code == 200
    assert second.status_code == 429
    assert "Next run is allowed at" in second.json()["detail"]


def test_collector_api_records_failed_run_and_returns_502():
    collector = TestCollector(error=RuntimeError("fixture service unavailable"))
    with make_client({collector.name: collector}) as client:
        response = client.post("/collectors/test-source/run", json={})
        runs_response = client.get("/collectors/runs")

    assert response.status_code == 502
    assert "fixture service unavailable" in response.json()["detail"]
    assert runs_response.json()[0]["error"] == "fixture service unavailable"
