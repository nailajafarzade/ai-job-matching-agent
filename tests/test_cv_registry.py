import yaml
import pytest

from app.analysis.vocabulary import get_vocabulary
from app.config import CV_REGISTRY_PATH
from app.documents.cv_registry import load_cv_registry
from app.profile.loader import load_profile


@pytest.fixture
def profile():
    return load_profile()


def write_registry(tmp_path, entries):
    path = tmp_path / "cvs.yaml"
    path.write_text(yaml.safe_dump({"cvs": entries}), encoding="utf-8")
    return path


def entry(**overrides):
    item = {
        "id": "java_backend",
        "file": "missing.pdf",
        "target_roles": ["Java Backend Developer"],
        "emphasis_skills": ["Java", "Spring Boot"],
    }
    item.update(overrides)
    return item


def test_example_registry_loads_and_missing_pdfs_are_warnings(profile):
    registry = load_cv_registry(CV_REGISTRY_PATH, profile, get_vocabulary())

    assert [cv.id for cv in registry.entries] == ["java_backend", "python_ai", "fullstack"]
    assert len(registry.warnings) == 3
    assert all("CV file is missing" in warning for warning in registry.warnings)


def test_registry_rejects_duplicate_ids(tmp_path, profile):
    path = write_registry(tmp_path, [entry(), entry(file="second.pdf")])

    with pytest.raises(ValueError, match="listed twice"):
        load_cv_registry(path, profile, get_vocabulary())


def test_registry_rejects_emphasis_skill_outside_vocabulary(tmp_path, profile):
    path = write_registry(tmp_path, [entry(emphasis_skills=["Not A Skill"])])

    with pytest.raises(ValueError, match="not in skills.yaml"):
        load_cv_registry(path, profile, get_vocabulary())


def test_registry_rejects_emphasis_skill_outside_profile(tmp_path, profile):
    path = write_registry(tmp_path, [entry(emphasis_skills=["Kafka"])])

    with pytest.raises(ValueError, match="not in profile.yaml"):
        load_cv_registry(path, profile, get_vocabulary())


def test_registry_rejects_target_role_outside_profile(tmp_path, profile):
    path = write_registry(tmp_path, [entry(target_roles=["Machine Learning Engineer"])])

    with pytest.raises(ValueError, match="target role.*not in profile.yaml"):
        load_cv_registry(path, profile, get_vocabulary())
