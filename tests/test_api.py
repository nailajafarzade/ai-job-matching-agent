"""API integration tests using the fast fake embedder."""
from datetime import datetime, timezone
from pathlib import Path
from shutil import copyfile

from fastapi.testclient import TestClient

from app.main import create_app
from tests.fakes import HashingEmbedder


def make_client(profile_path: Path | None = None) -> TestClient:
    app = create_app(
        embedder=HashingEmbedder(),
        database_url="sqlite:///:memory:",
        profile_path=profile_path or Path(__file__).parent.parent / "data" / "profile.yaml",
        min_score=0,
    )
    return TestClient(app)


def good_job(**overrides) -> dict:
    data = {
        "title": "Junior Java Backend Developer",
        "company": "Example Tech",
        "description": (
            "We need a junior Java backend developer. Requirements: Java, Spring Boot, "
            "PostgreSQL, REST API, Docker, Kafka, and Kubernetes. Build backend services "
            "with our team. Zero to two years of experience is welcome."
        ),
        "remote_type": "remote",
        "remote_work_eligibility": "eligible",
        "eligible_countries": ["Azerbaijan"],
    }
    data.update(overrides)
    return data


def assert_same_match(actual: dict, expected: dict) -> None:
    actual_created = datetime.fromisoformat(actual["created_at"].replace("Z", "+00:00"))
    expected_created = datetime.fromisoformat(expected["created_at"].replace("Z", "+00:00"))
    if actual_created.tzinfo is None:
        actual_created = actual_created.replace(tzinfo=timezone.utc)
    if expected_created.tzinfo is None:
        expected_created = expected_created.replace(tzinfo=timezone.utc)

    actual_fields = {key: value for key, value in actual.items() if key != "created_at"}
    expected_fields = {key: value for key, value in expected.items() if key != "created_at"}
    assert actual_fields == expected_fields
    assert actual_created == expected_created


def test_health_submit_and_duplicate():
    with make_client() as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"
        assert health.json()["embedding_model"] == "hashing-test-embedder"
        assert health.json()["profile_version"] == 3

        first = client.post("/jobs", json=good_job())
        assert first.status_code == 201
        result = first.json()
        assert result["duplicate"] is False
        assert result["match"]["final_score"] is not None
        assert 0 <= result["match"]["final_score"] <= 100
        assert result["match"]["matched_skills"]
        assert "Kafka" in result["match"]["missing_skills"]
        assert result["match"]["explanation"]

        duplicate = client.post("/jobs", json=good_job())
        assert duplicate.status_code == 200
        assert duplicate.json()["duplicate"] is True
        assert duplicate.json()["job"]["id"] == result["job"]["id"]
        assert len(client.get("/jobs").json()) == 1


def test_submit_preserves_source_and_application_email():
    with make_client() as client:
        response = client.post(
            "/jobs",
            json=good_job(source="remotive", apply_email="apply@example.com"),
        )
        assert response.status_code == 201
        assert response.json()["job"]["source"] == "remotive"
        assert response.json()["job"]["apply_email"] == "apply@example.com"


def test_rejected_unknown_remote_and_short_description():
    with make_client() as client:
        senior = good_job(title="Senior Java Developer")
        senior_result = client.post("/jobs", json=senior).json()
        senior_match = senior_result["match"]
        assert senior_match["decision"] == "rejected"
        assert senior_match["final_score"] is None
        assert senior_match["skill_score"] is None
        assert senior_match["semantic_score"] is None
        assert senior_match["title_score"] is None

        unknown = good_job(
            company="Unknown Remote Inc",
            remote_work_eligibility="unknown",
            eligible_countries=[],
        )
        unknown_result = client.post("/jobs", json=unknown)
        assert unknown_result.status_code == 201
        assert unknown_result.json()["match"]["decision"] == "needs_review"

        short = client.post("/jobs", json=good_job(description="Too short"))
        assert short.status_code == 422


def test_job_filters_and_missing_jobs():
    with make_client() as client:
        good = client.post("/jobs", json=good_job()).json()
        client.post("/jobs", json=good_job(title="Senior Java Developer", company="Senior Co"))

        rejected = client.get("/jobs", params={"decision": "rejected"})
        assert rejected.status_code == 200
        assert len(rejected.json()) == 1
        assert rejected.json()[0]["match"]["decision"] == "rejected"

        high_score = client.get("/jobs", params={"min_score": 100})
        assert high_score.status_code == 200
        assert good["match"]["final_score"] < 100
        assert high_score.json() == []

        assert client.get("/jobs/999").status_code == 404
        assert client.post("/jobs/999/rematch").status_code == 404
        assert good["job"]["id"] > 0


def test_rematch_adds_history_without_changing_old_match():
    with make_client() as client:
        submitted = client.post("/jobs", json=good_job()).json()
        job_id = submitted["job"]["id"]
        original_match = submitted["match"]

        rematched = client.post(f"/jobs/{job_id}/rematch")
        assert rematched.status_code == 200
        matches = client.get(f"/jobs/{job_id}/matches").json()
        assert len(matches) == 2
        assert_same_match(matches[0], original_match)
        assert matches[1]["id"] == rematched.json()["match"]["id"]


def test_profile_reload_and_rematch_uses_new_profile(tmp_path):
    profile_path = tmp_path / "profile.yaml"
    copyfile(Path(__file__).parent.parent / "data" / "profile.yaml", profile_path)

    with make_client(profile_path) as client:
        submitted = client.post("/jobs", json=good_job()).json()
        job_id = submitted["job"]["id"]
        old_match = submitted["match"]
        assert "Kafka" in old_match["missing_skills"]

        profile_text = profile_path.read_text(encoding="utf-8")
        profile_text = profile_text.replace("version: 3", "version: 4", 1)
        profile_text = profile_text.replace(
            "  - {name: Redis,",
            "  - {name: Kafka, level: hands_on}\n  - {name: Redis,",
            1,
        )
        profile_path.write_text(profile_text, encoding="utf-8")

        reloaded = client.post("/profile/reload")
        assert reloaded.status_code == 200
        assert reloaded.json() == {"old_version": 3, "new_version": 4}

        rematched = client.post(f"/jobs/{job_id}/rematch").json()
        assert rematched["match"]["profile_version"] == 4
        assert "Kafka" in rematched["match"]["matched_skills"]
        matches = client.get(f"/jobs/{job_id}/matches").json()
        assert [match["profile_version"] for match in matches] == [3, 4]
        assert_same_match(matches[0], old_match)


def test_broken_profile_reload_keeps_app_working(tmp_path):
    profile_path = tmp_path / "profile.yaml"
    copyfile(Path(__file__).parent.parent / "data" / "profile.yaml", profile_path)

    with make_client(profile_path) as client:
        profile_path.write_text(
            profile_path.read_text(encoding="utf-8").replace("name: Java,", "name: UnknownSkill,"),
            encoding="utf-8",
        )
        response = client.post("/profile/reload")
        assert response.status_code == 422
        assert "UnknownSkill" in response.json()["detail"]
        assert client.get("/profile").json()["version"] == 3
        assert client.get("/health").status_code == 200
