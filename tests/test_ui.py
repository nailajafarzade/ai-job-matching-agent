from pathlib import Path

from fastapi.testclient import TestClient

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


def submit_job(client: TestClient, company: str = "Dashboard Example") -> int:
    response = client.post(
        "/jobs",
        json={
            "title": "Junior Java Backend Developer",
            "company": company,
            "url": "https://example.test/jobs/123",
            "description": (
                "We need a junior Java backend developer. Requirements include Java, Spring Boot, "
                "PostgreSQL and REST API. Build backend services with our team."
            ),
            "remote_type": "remote",
            "remote_work_eligibility": "eligible",
            "eligible_countries": ["Azerbaijan"],
        },
    )
    assert response.status_code == 201
    return response.json()["job"]["id"]


def test_dashboard_shows_job_scores_and_filters():
    with make_client() as client:
        job_id = submit_job(client)
        job_result = client.get(f"/jobs/{job_id}").json()
        score = job_result["match"]["final_score"]

        response = client.get("/ui")

        assert response.status_code == 200
        assert "Junior Java Backend Developer" in response.text
        assert f"{score:.1f}" in response.text
        assert client.get("/ui", params={"decision": "queued"}).status_code == 200
        assert client.get("/ui", params={"decision": "rejected"}).text.count("Junior Java Backend Developer") == 0
        assert client.get("/ui/static/style.css").status_code == 200


def test_dashboard_escapes_untrusted_job_fields():
    with make_client() as client:
        job_id = submit_job(client, company="<script>alert(1)</script>")

        response = client.get(f"/ui/jobs/{job_id}")

        assert response.status_code == 200
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text
        assert "<script>alert(1)</script>" not in response.text


def test_job_detail_prepare_approve_and_track_through_forms():
    with make_client() as client:
        job_id = submit_job(client)
        detail = client.get(f"/ui/jobs/{job_id}")
        assert detail.status_code == 200
        assert "Matched skills" in detail.text
        assert "Original post" in detail.text

        prepared = client.post(f"/ui/jobs/{job_id}/prepare", follow_redirects=False)
        assert prepared.status_code == 303
        detail = client.get(prepared.headers["location"])
        assert detail.status_code == 200
        assert "CV choice reason" in detail.text
        assert "Cover letter" in detail.text
        assert "No issues." in detail.text

        application_id = client.get("/applications").json()[0]["id"]
        approved = client.post(
            f"/ui/applications/{application_id}/approve",
            data={"note": "Reviewed by owner"},
            follow_redirects=False,
        )
        assert approved.status_code == 303
        assert "Application approved." in client.get(approved.headers["location"]).text
        assert client.get(f"/applications/{application_id}").json()["status"] == "approved"

        sent = client.post(
            f"/ui/applications/{application_id}/status",
            data={"status": "sent", "note": "Applied manually"},
            follow_redirects=False,
        )
        assert sent.status_code == 303
        assert client.get(f"/applications/{application_id}").json()["status"] == "sent"
        detail = client.get(sent.headers["location"])
        assert "Applied manually" in detail.text


def test_needs_review_form_requires_and_displays_eligibility_error():
    with make_client() as client:
        job_id = submit_job(client, company="Eligibility Dashboard Co")
        # A second post with uncertain eligibility uses the normal analysis pipeline.
        submitted = client.post(
            "/jobs",
            json={
                "title": "Junior Java Backend Developer",
                "company": "Unknown Dashboard Co",
                "description": (
                    "We need a junior Java backend developer. Requirements include Java, Spring Boot, "
                    "PostgreSQL and REST API. Build backend services with our team."
                ),
                "remote_type": "remote",
                "remote_work_eligibility": "unknown",
                "eligible_countries": [],
            },
        )
        assert submitted.status_code == 201
        uncertain_job_id = submitted.json()["job"]["id"]
        prepared = client.post(f"/ui/jobs/{uncertain_job_id}/prepare", follow_redirects=False)
        assert prepared.status_code == 303
        application_id = client.get("/applications", params={"status": "prepared"}).json()[0]["id"]

        refused = client.post(
            f"/ui/applications/{application_id}/approve",
            data={},
            follow_redirects=False,
        )
        assert refused.status_code == 303
        detail = client.get(refused.headers["location"])
        assert "eligibility_checked=true" in detail.text
        assert "I checked the eligibility" in detail.text
        assert client.get(f"/ui/jobs/{job_id}").status_code == 200


def test_dashboard_stats_page_renders_tables():
    with make_client() as client:
        job_id = submit_job(client)
        client.post(f"/ui/jobs/{job_id}/prepare")

        response = client.get("/ui/stats")

        assert response.status_code == 200
        assert "Applications by status" in response.text
        assert "Applications per week" in response.text
        assert "Average final score" in response.text
