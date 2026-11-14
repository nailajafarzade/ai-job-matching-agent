from pathlib import Path
import re

from fastapi.testclient import TestClient
import pytest

from app.db.models import Application
from app.main import create_app
from tests.fakes import HashingEmbedder


def make_client() -> TestClient:
    app = create_app(
        embedder=HashingEmbedder(),
        database_url="sqlite:///:memory:",
        profile_path=Path(__file__).parent.parent / "data" / "profile.yaml",
        min_score=0,
    )
    return TestClient(app)


def good_job(**overrides) -> dict:
    data = {
        "title": "Junior Java Backend Developer",
        "company": "Example Tech",
        "description": (
            "We need a junior Java backend developer. Requirements include Java, Spring Boot, "
            "PostgreSQL and REST API. Build backend services with our team."
        ),
        "remote_type": "remote",
        "remote_work_eligibility": "eligible",
        "eligible_countries": ["Azerbaijan"],
    }
    data.update(overrides)
    return data


def prepare_job(client: TestClient, **job_overrides) -> dict:
    submitted = client.post("/jobs", json=good_job(**job_overrides))
    assert submitted.status_code == 201
    prepared = client.post(f"/jobs/{submitted.json()['job']['id']}/prepare")
    assert prepared.status_code == 201
    return prepared.json()


def test_approval_is_refused_when_letter_review_has_an_error():
    with make_client() as client:
        application = prepare_job(client)
        with client.app.state.session_factory() as session:
            saved = session.get(Application, application["id"])
            saved.review_issues = [{"level": "error", "message": "Unsupported skill claim"}]
            session.commit()

        response = client.post(f"/applications/{application['id']}/approve")

        assert response.status_code == 409
        assert "review contains errors" in response.json()["detail"]


def test_needs_review_requires_eligibility_confirmation_then_can_be_approved():
    with make_client() as client:
        application = prepare_job(
            client,
            company="Unknown Eligibility Co",
            remote_work_eligibility="unknown",
            eligible_countries=[],
        )
        assert any(issue["level"] == "warning" for issue in application["review_issues"])

        refused = client.post(f"/applications/{application['id']}/approve")
        assert refused.status_code == 409
        assert "eligibility_checked=true" in refused.json()["detail"]

        approved = client.post(
            f"/applications/{application['id']}/approve",
            json={"eligibility_checked": True},
        )
        assert approved.status_code == 200
        assert approved.json()["status"] == "approved"


def test_approval_requires_cv_and_letter():
    with make_client() as client:
        application = prepare_job(client)
        with client.app.state.session_factory() as session:
            saved = session.get(Application, application["id"])
            saved.cv_id = None
            saved.letter_text = None
            session.commit()

        response = client.post(f"/applications/{application['id']}/approve")

        assert response.status_code == 409
        assert "no letter" in response.json()["detail"]
        assert "no CV" in response.json()["detail"]


def test_status_history_listing_filters_and_pagination():
    with make_client() as client:
        first = prepare_job(client, company="First Co")
        second = prepare_job(client, company="Second Co")

        approved = client.post(f"/applications/{first['id']}/approve")
        assert approved.status_code == 200
        changed = client.post(
            f"/applications/{first['id']}/status",
            json={"status": "package_ready", "note": "Package checked"},
        )
        assert changed.status_code == 200
        assert changed.json()["status"] == "package_ready"

        illegal = client.post(
            f"/applications/{first['id']}/status",
            json={"status": "prepared"},
        )
        assert illegal.status_code == 409

        prepared_page = client.get("/applications", params={"status": "prepared", "limit": 1})
        assert prepared_page.status_code == 200
        assert len(prepared_page.json()) == 1
        assert prepared_page.json()[0]["id"] == second["id"]
        assert client.get("/applications", params={"status": "package_ready"}).json()[0]["id"] == first["id"]

        events = client.get(f"/applications/{first['id']}/events")
        assert events.status_code == 200
        assert [event["to_status"] for event in events.json()] == ["prepared", "approved", "package_ready"]
        assert events.json()[-1]["note"] == "Package checked"
        assert client.get("/applications/999/events").status_code == 404


def test_skip_endpoint_records_status_and_event():
    with make_client() as client:
        application = prepare_job(client)

        skipped = client.post(f"/applications/{application['id']}/skip", json={"note": "Not a fit"})

        assert skipped.status_code == 200
        assert skipped.json()["status"] == "skipped"
        events = client.get(f"/applications/{application['id']}/events").json()
        assert events[-1]["to_status"] == "skipped"
        assert events[-1]["note"] == "Not a fit"


def test_stats_counts_latest_decisions_scores_and_iso_weeks():
    with make_client() as client:
        first = prepare_job(client, company="First Stats Co")
        second = prepare_job(client, company="Second Stats Co")
        client.post(f"/applications/{first['id']}/approve")
        rejected = client.post("/jobs", json=good_job(title="Senior Java Developer", company="Rejected Co"))
        assert rejected.status_code == 201

        response = client.get("/stats")

        assert response.status_code == 200
        result = response.json()
        assert result["applications_by_status"]["prepared"] == 1
        assert result["applications_by_status"]["approved"] == 1
        assert result["matches_by_decision"]["queued"] == 2
        assert result["matches_by_decision"]["rejected"] == 1
        first_score = client.get(f"/jobs/{first['job_id']}").json()["match"]["final_score"]
        second_score = client.get(f"/jobs/{second['job_id']}").json()["match"]["final_score"]
        assert result["average_final_score"] == pytest.approx((first_score + second_score) / 2)
        assert sum(item["count"] for item in result["applications_per_week"]) == 2
        assert all(re.fullmatch(r"\d{4}-W\d{2}", item["week"]) for item in result["applications_per_week"])
