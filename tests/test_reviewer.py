from types import SimpleNamespace

from app.analysis.vocabulary import get_vocabulary
from app.documents.facts import build_facts
from app.documents.letter import TemplateLetterWriter
from app.documents.reviewer import review_letter
from app.profile.loader import load_profile
from app.schemas.analysis import AnalysisResult


def clean_letter():
    profile = load_profile()
    job = SimpleNamespace(title="Junior Java Backend Developer", company="Example Tech", decision="queued")
    facts = build_facts(job, AnalysisResult(required_skills=["Java", "OpenAI API"]), profile)
    letter = TemplateLetterWriter().write(job, facts, profile)
    return job, profile, letter


def test_good_letter_has_no_issues():
    job, profile, letter = clean_letter()

    assert review_letter(letter, job, profile, get_vocabulary()) == []


def test_reviewer_rejects_missing_skill_and_years_claim():
    job, profile, letter = clean_letter()

    issues = review_letter(letter + " I know Kafka and have 4 years of experience.", job, profile, get_vocabulary())

    assert any("Kafka" in issue.message for issue in issues)
    assert any("years-of-experience" in issue.message for issue in issues)
    short_claim_issues = review_letter(letter + " I have 5+ years in Java.", job, profile, get_vocabulary())
    assert any("years-of-experience" in issue.message for issue in short_claim_issues)


def test_reviewer_rejects_studied_skill_outside_learning_sentence():
    job, profile, letter = clean_letter()

    issues = review_letter(letter + " I know OpenAI API.", job, profile, get_vocabulary())

    assert any("outside the learning sentence" in issue.message for issue in issues)


def test_reviewer_rejects_placeholders_and_warns_for_review_jobs():
    job, profile, letter = clean_letter()
    job.decision = "needs_review"

    issues = review_letter(letter + " TODO None", job, profile, get_vocabulary())

    assert any("placeholder" in issue.message for issue in issues)
    assert any(issue.level == "warning" and "manual review" in issue.message for issue in issues)


def test_reviewer_requires_company_and_title_and_warns_for_long_letters():
    job, profile, letter = clean_letter()
    job.company = "Different Company"
    job.title = "Different Job Title"

    issues = review_letter(letter + " more" * 201, job, profile, get_vocabulary())

    assert any("does not name the company" in issue.message for issue in issues)
    assert any("does not name the job title" in issue.message for issue in issues)
    assert any(issue.level == "warning" and "longer than 200" in issue.message for issue in issues)
