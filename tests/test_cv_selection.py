from types import SimpleNamespace

from app.analysis.vocabulary import get_vocabulary
from app.config import CV_REGISTRY_PATH
from app.documents.cv_registry import load_cv_registry
from app.documents.cv_selection import select_cv
from app.profile.loader import load_profile
from app.schemas.analysis import AnalysisResult


def select(title, required):
    profile = load_profile()
    vocabulary = get_vocabulary()
    registry = load_cv_registry(CV_REGISTRY_PATH, profile, vocabulary)
    job = SimpleNamespace(title=title)
    analysis = AnalysisResult(required_skills=required)
    return select_cv(job, analysis, registry, vocabulary)


def test_java_job_selects_java_backend_cv():
    choice = select("Junior Java Backend Developer", ["Java", "Spring Boot", "PostgreSQL"])

    assert choice.cv_id == "java_backend"
    assert choice.score > 0
    assert "Java" in choice.reason


def test_ai_job_selects_python_ai_cv():
    choice = select("Machine Learning Intern", ["Python", "Machine Learning"])

    assert choice.cv_id == "python_ai"
    assert choice.score > 0


def test_no_overlap_uses_first_cv_with_reason():
    choice = select("Quantum Researcher", ["Kafka"])

    assert choice.cv_id == "java_backend"
    assert choice.score == 0
    assert "fallback" in choice.reason
