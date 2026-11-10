"""Tests for the evaluation counts using the fake embedder."""
from app.analysis.analyzer import get_analyzer
from app.analysis.vocabulary import get_vocabulary
from app.matching.scorer import Matcher
from app.matching.types import JobFacts
from app.profile.loader import load_profile
from app.schemas.enums import RemoteEligibility, RemoteType
from scripts.evaluate import evaluate_job, summarize
from tests.fakes import HashingEmbedder


def make_matcher() -> Matcher:
    return Matcher(load_profile(), get_vocabulary(), HashingEmbedder(), min_score=0)


def make_job(title: str, eligibility=RemoteEligibility.eligible) -> JobFacts:
    return JobFacts(
        title=title,
        description=(
            "Requirements include Java, Spring Boot, PostgreSQL, and REST API development. "
            "Junior applicants are welcome."
        ),
        remote_type=RemoteType.remote,
        remote_work_eligibility=eligibility,
    )


def test_summary_counts_apply_review_skip_queue_and_disagreements():
    matcher = make_matcher()
    analyzer = get_analyzer()
    rows = [
        evaluate_job(make_job("Junior Java Backend Developer"), "skip", matcher, analyzer),
        evaluate_job(
            make_job("Junior Python Backend Developer", RemoteEligibility.unknown),
            "apply",
            matcher,
            analyzer,
        ),
        evaluate_job(make_job("Senior Java Developer"), "apply", matcher, analyzer),
    ]

    summary = summarize(rows)

    assert summary.apply_queued == 0
    assert summary.apply_needs_review == 1
    assert summary.skip_queued == 1
    assert [row.title for row in summary.disagreements] == [
        "Junior Java Backend Developer",
        "Senior Java Developer",
    ]


def test_summary_averages_available_scores_and_ignores_rejected_scores():
    matcher = make_matcher()
    analyzer = get_analyzer()
    queued = evaluate_job(make_job("Junior Java Backend Developer"), "apply", matcher, analyzer)
    rejected = evaluate_job(make_job("Senior Java Developer"), "skip", matcher, analyzer)

    summary = summarize([queued, rejected])

    assert summary.apply_queued == 1
    assert summary.skip_queued == 0
    assert summary.average_apply_score == queued.final_score
    assert summary.average_skip_score is None
    assert summary.disagreements == []
