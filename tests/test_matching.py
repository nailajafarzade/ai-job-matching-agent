import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.analyzer import get_analyzer
from app.analysis.vocabulary import get_vocabulary
from app.db.models import Job, Match
from app.db.session import Base, make_engine
from app.intake.hashing import compute_content_hash
from app.matching.scorer import Matcher, build_job_text
from app.matching.similarity import scale
from app.matching.skills_score import score_skills
from app.matching.types import JobFacts
from app.profile.loader import load_profile
from app.schemas.analysis import AnalysisResult
from app.schemas.enums import MatchDecision, RemoteEligibility, RemoteType, Seniority
from app.schemas.match import MatchRead
from tests.fakes import HashingEmbedder
from tests.test_analysis import JOB as JOB_TEXT


@pytest.fixture(scope="module")
def profile():
    return load_profile()


@pytest.fixture(scope="module")
def vocab():
    return get_vocabulary()


@pytest.fixture()
def embedder():
    return HashingEmbedder()


def make_matcher(profile, vocab, embedder, **kw) -> Matcher:
    return Matcher(profile, vocab, embedder, **kw)


def remote_job(title="Junior Java Backend Developer", description=JOB_TEXT, **kw) -> JobFacts:
    base = dict(title=title, description=description, remote_type=RemoteType.remote,
                remote_work_eligibility=RemoteEligibility.eligible)
    base.update(kw)
    return JobFacts(**base)


# ---------- scale ----------

def test_scale_is_a_cut_straight_line():
    assert scale(0.15, 0.15, 0.60) == 0
    assert scale(0.60, 0.15, 0.60) == 100
    assert scale(0.375, 0.15, 0.60) == 50
    assert scale(0.0, 0.15, 0.60) == 0
    assert scale(0.99, 0.15, 0.60) == 100
    with pytest.raises(ValueError):
        scale(0.5, 0.6, 0.6)


# ---------- skill score ----------

def test_skill_score_by_hand(profile, vocab):
    # required: Java 3, Spring Boot 3, PostgreSQL 3, REST API 3, Docker 2 (I know all)
    # nice (x0.4): Kafka 2 (missing), Kubernetes 2 (missing), AWS 2 (I know)
    # total = 14 + 0.4*6 = 16.4, earned = 14 + 0.4*2 = 14.8
    result = get_analyzer().analyze("Junior Java Backend Developer", JOB_TEXT)
    skills = score_skills(result, profile, vocab.weights)
    assert skills.score == pytest.approx(100 * 14.8 / 16.4, abs=0.01)
    assert skills.matched == ["Java", "Spring Boot", "PostgreSQL", "REST API", "Docker", "AWS"]
    assert skills.missing == ["Kafka", "Kubernetes"]
    assert skills.studied == []


def test_studied_skill_gives_half_credit_and_is_listed_separately(profile, vocab):
    skills = score_skills(AnalysisResult(required_skills=["Java", "LLM"]), profile, vocab.weights)
    # Java 3 full, LLM 3 half -> (3 + 1.5) / 6
    assert skills.score == pytest.approx(75.0)
    assert skills.matched == ["Java"] and skills.studied == ["LLM"] and skills.missing == []


def test_related_skill_gives_no_credit(profile, vocab):
    # Jenkins is related to CI/CD, but I never listed Jenkins.
    skills = score_skills(AnalysisResult(required_skills=["Jenkins", "Dockerfile"]), profile, vocab.weights)
    assert skills.score == 0 and skills.missing == ["Jenkins", "Dockerfile"]


def test_missing_skill_is_never_added_to_profile(profile, vocab):
    before = dict(profile.skills)
    score_skills(AnalysisResult(required_skills=["Kafka"]), profile, vocab.weights)
    assert profile.skills == before and "Kafka" not in profile.skills


def test_no_known_skill_gives_none(profile, vocab):
    assert score_skills(AnalysisResult(), profile, vocab.weights).score is None


# ---------- matcher ----------

def run(profile, vocab, embedder, job: JobFacts, **matcher_kw):
    analysis = get_analyzer().analyze(job.title, job.description)
    return make_matcher(profile, vocab, embedder, **matcher_kw).match(job, analysis)


def test_good_job_is_queued_with_all_parts(profile, vocab, embedder):
    result = run(profile, vocab, embedder, remote_job(), min_score=0)
    assert result.decision == MatchDecision.queued
    for part in (result.final_score, result.skill_score, result.semantic_score, result.title_score):
        assert part is not None and 0 <= part <= 100
    assert result.matched_skills[:2] == ["Java", "Spring Boot"]
    assert result.missing_skills == ["Kafka", "Kubernetes"]
    assert sum(result.weights.values()) == pytest.approx(1.0, abs=0.001)
    assert result.profile_version == 3 and result.embedding_model == embedder.name
    assert "Missing: Kafka, Kubernetes." in result.explanation


def test_final_score_is_the_weighted_sum(profile, vocab, embedder):
    result = run(profile, vocab, embedder, remote_job(), min_score=0)
    w = result.weights
    expected = w["skill"] * result.skill_score + w["semantic"] * result.semantic_score + w["title"] * result.title_score
    assert result.final_score == pytest.approx(expected, abs=0.02)


def test_below_threshold(profile, vocab, embedder):
    result = run(profile, vocab, embedder, remote_job(), min_score=101)
    assert result.decision == MatchDecision.below_threshold


def test_unknown_remote_eligibility_gives_needs_review(profile, vocab, embedder):
    job = remote_job(remote_work_eligibility=RemoteEligibility.unknown)
    result = run(profile, vocab, embedder, job, min_score=0)
    assert result.decision == MatchDecision.needs_review
    assert result.review_reasons and "Check by hand" in result.explanation


def test_rejected_job_has_no_scores_and_no_embedding_work(profile, vocab, embedder):
    matcher = make_matcher(profile, vocab, embedder)
    calls_after_setup = embedder.calls
    job = remote_job(title="Senior Java Developer")
    result = matcher.match(job, get_analyzer().analyze(job.title, job.description))
    assert result.decision == MatchDecision.rejected
    assert result.final_score is None and result.skill_score is None
    assert result.semantic_score is None and result.title_score is None
    assert "Seniority" in result.reject_reasons[0]
    assert embedder.calls == calls_after_setup


def test_profile_texts_are_embedded_once_not_per_job(profile, vocab, embedder):
    matcher = make_matcher(profile, vocab, embedder)
    setup_calls = embedder.calls
    for _ in range(3):
        job = remote_job()
        matcher.match(job, get_analyzer().analyze(job.title, job.description))
    assert embedder.calls == setup_calls + 3 * 2  # one for the job text, one for the title


def test_no_known_skill_drops_the_skill_weight(profile, vocab, embedder):
    job = remote_job(title="Backend Developer", description="We build things with great people every day.")
    result = run(profile, vocab, embedder, job, min_score=0)
    assert result.skill_score is None
    assert set(result.weights) == {"semantic", "title"}
    assert sum(result.weights.values()) == pytest.approx(1.0, abs=0.001)
    assert "skill score is not used" in result.explanation


def test_title_priority_changes_title_score(profile, vocab, embedder):
    matcher = make_matcher(profile, vocab, embedder)
    high = matcher.index.title("Java Backend Developer")        # exact, priority high
    secondary = matcher.index.title("Full Stack Developer")     # exact, priority secondary
    assert high.score == 100 and high.closest == "Java Backend Developer"
    assert secondary.score == pytest.approx(70.0) and secondary.closest == "Full Stack Developer"


def test_job_text_skips_about_us_and_benefits_and_is_cut():
    text = build_job_text(JobFacts(title="Java Developer", description=JOB_TEXT))
    assert "fintech" not in text and "Free lunch" not in text and "Spring Boot" in text
    long = build_job_text(JobFacts(title="T", description="Requirements:\n" + "Java and Spring. " * 500))
    assert len(long) == 1200


def test_result_is_saved_and_read_back(profile, vocab, embedder):
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    result = run(profile, vocab, embedder, remote_job(), min_score=0)
    with Session(engine) as s:
        job = Job(title="J", company="C", description_raw="d", content_hash=compute_content_hash("C", "J", "d"))
        s.add(job)
        s.commit()
        s.add(result.to_orm(job.id))
        s.commit()
        saved = s.scalars(select(Match)).one()
        read = MatchRead.model_validate(saved)
    assert read.final_score == result.final_score
    assert read.matched_skills == result.matched_skills and read.missing_skills == result.missing_skills
    assert read.weights == result.weights and read.matcher_version == result.matcher_version


def test_rejected_result_is_saved_without_scores(profile, vocab, embedder):
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    result = run(profile, vocab, embedder, remote_job(title="Senior Java Developer"))
    with Session(engine) as s:
        job = Job(title="J", company="C", description_raw="d", content_hash="h")
        s.add(job)
        s.commit()
        s.add(result.to_orm(job.id))
        s.commit()
        read = MatchRead.model_validate(s.scalars(select(Match)).one())
    assert read.decision == MatchDecision.rejected and read.final_score is None
