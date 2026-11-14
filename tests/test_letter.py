from dataclasses import replace
from types import SimpleNamespace

from app.analysis.vocabulary import get_vocabulary
from app.documents.facts import build_facts
from app.documents.letter import TemplateLetterWriter
from app.documents.reviewer import review_letter
from app.profile.loader import load_profile
from app.schemas.analysis import AnalysisResult


def make_letter(analysis):
    profile = load_profile()
    job = SimpleNamespace(title="Junior Java Backend Developer", company="Example Tech")
    facts = build_facts(job, analysis, profile)
    return job, profile, facts, TemplateLetterWriter().write(job, facts, profile)


def test_template_letter_is_short_honest_and_mentions_team_project():
    job, profile, facts, letter = make_letter(
        AnalysisResult(required_skills=["Java", "Spring Boot", "OpenAI API", "Kafka"])
    )

    assert len(letter.split()) <= 200
    assert "second-year IT student" in letter
    assert "Example Tech" in letter and job.title in letter
    assert "Kafka" not in letter
    assert "I am also learning OpenAI API" in letter
    assert "team" in letter
    assert review_letter(letter, job, profile, get_vocabulary()) == []


def test_template_letter_omits_empty_hands_on_sentence_and_null_project_role():
    job, profile, facts, _ = make_letter(AnalysisResult(required_skills=["OpenAI API"]))
    no_role_project = replace(facts.best_project, role=None)
    facts = replace(facts, hands_on_matches=[], best_project=no_role_project)

    letter = TemplateLetterWriter().write(job, facts, profile)

    assert "hands-on skills" not in letter
    assert "I contributed" in letter
    assert "worked as" not in letter


def test_template_letter_without_hands_on_skills_remains_under_word_limit():
    job, profile, _, letter = make_letter(AnalysisResult(required_skills=["Kafka"]))

    assert "hands-on skills" not in letter
    assert len(letter.split()) <= 200
    assert "Kafka" not in letter
