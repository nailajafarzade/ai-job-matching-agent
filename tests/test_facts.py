from types import SimpleNamespace

from app.documents.facts import build_facts
from app.profile.loader import load_profile
from app.schemas.analysis import AnalysisResult


def test_facts_sort_skills_cap_lists_and_use_confirmed_project_stack():
    profile = load_profile()
    analysis = AnalysisResult(
        required_skills=[
            "HTML", "Java", "CSS", "Python", "FastAPI", "Spring Boot",
            "PostgreSQL", "OpenAI API", "LLM", "RAG", "Kafka",
        ],
        nice_to_have_skills=["Docker", "Redis", "LangChain"],
    )

    facts = build_facts(SimpleNamespace(title="Backend Developer"), analysis, profile)

    assert len(facts.hands_on_matches) == 5
    assert facts.hands_on_matches[:4] == ["Java", "Python", "FastAPI", "Spring Boot"]
    assert facts.studied_matches == ["LLM", "RAG", "LangChain"]
    assert facts.missing == ["Kafka"]
    assert facts.best_project.name == "MoneyQuest"
    assert facts.best_project.role == "Backend Developer"


def test_best_project_uses_only_confirmed_project_technologies():
    profile = load_profile()
    facts = build_facts(
        SimpleNamespace(title="AI Engineer Intern"),
        AnalysisResult(required_skills=["OpenAI API"]),
        profile,
    )

    assert facts.best_project.name == "Voyanta"
    assert "Team project" in facts.best_project.note


def test_facts_without_profile_projects_have_no_best_project():
    profile = load_profile()
    profile.projects.clear()

    facts = build_facts(
        SimpleNamespace(title="Backend Developer"),
        AnalysisResult(required_skills=["Java"]),
        profile,
    )

    assert facts.best_project is None
