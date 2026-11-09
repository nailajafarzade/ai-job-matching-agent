import copy

import pytest
import yaml

from app.analysis.vocabulary import get_vocabulary
from app.config import PROFILE_PATH
from app.matching.filters import apply_hard_filters, remote_eligibility
from app.matching.types import JobFacts
from app.profile.loader import load_profile, parse_profile
from app.schemas.analysis import AnalysisResult
from app.schemas.enums import RemoteEligibility, RemoteType, Seniority


@pytest.fixture(scope="module")
def profile():
    return load_profile()


def raw_profile() -> dict:
    with open(PROFILE_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------- profile loader ----------

def test_real_profile_loads(profile):
    assert profile.version == 3
    assert profile.level_of("Java") == "hands_on"
    assert profile.level_of("OpenAI API") == "studied"
    assert profile.level_of("Kafka") is None
    assert [t.label for t in profile.texts] == ["summary", "MoneyQuest", "Virtual Student", "Voyanta", "skills"]
    assert profile.excluded_job_countries == ["India"]


def test_loader_rejects_unknown_skill():
    data = raw_profile()
    data["skills"].append({"name": "Cobol", "level": "hands_on"})
    with pytest.raises(ValueError, match="not in skills.yaml"):
        parse_profile(data, get_vocabulary())


def test_loader_rejects_bad_level_and_duplicates():
    data = raw_profile()
    bad_level = copy.deepcopy(data)
    bad_level["skills"][0]["level"] = "expert"
    with pytest.raises(ValueError, match="level"):
        parse_profile(bad_level, get_vocabulary())

    duplicate = copy.deepcopy(data)
    duplicate["skills"].append(dict(duplicate["skills"][0]))
    with pytest.raises(ValueError, match="twice"):
        parse_profile(duplicate, get_vocabulary())


def test_semantic_texts_use_only_hands_on_skills(profile):
    skills_text = profile.texts[-1].text
    assert "Java" in skills_text and "Prompt Engineering" in skills_text
    assert "OpenAI API" not in skills_text and "RAG" not in skills_text  # studied only


# ---------- hard filters ----------

def job(**kw) -> JobFacts:
    base = dict(title="Backend Developer", description="x" * 40, remote_type=RemoteType.remote,
                remote_work_eligibility=RemoteEligibility.eligible)
    base.update(kw)
    return JobFacts(**base)


def analysis(**kw) -> AnalysisResult:
    return AnalysisResult(**kw)


@pytest.mark.parametrize("level", ["senior", "lead", "principal", "staff", "manager"])
def test_rejects_senior_levels(profile, level):
    result = apply_hard_filters(job(), analysis(seniority=Seniority(level)), profile)
    assert result.rejected and level in result.reject_reasons[0]


@pytest.mark.parametrize("level", ["intern", "junior", "mid", "unknown"])
def test_accepts_other_levels(profile, level):
    assert not apply_hard_filters(job(), analysis(seniority=Seniority(level)), profile).rejected


def test_years_limit(profile):
    assert apply_hard_filters(job(), analysis(min_years=3), profile).rejected
    assert not apply_hard_filters(job(), analysis(min_years=2), profile).rejected
    assert not apply_hard_filters(job(), analysis(min_years=0), profile).rejected
    assert not apply_hard_filters(job(), analysis(min_years=None), profile).rejected


def test_excluded_country_by_country_or_location(profile):
    assert apply_hard_filters(job(country="India"), analysis(), profile).rejected
    assert apply_hard_filters(job(location="Bangalore, India"), analysis(), profile).rejected
    assert apply_hard_filters(job(country="india"), analysis(), profile).rejected


def test_indiana_is_not_india(profile):
    result = apply_hard_filters(job(location="Indianapolis, Indiana"), analysis(), profile)
    assert not result.rejected


def test_remote_not_eligible_is_rejected(profile):
    j = job(remote_work_eligibility=RemoteEligibility.not_eligible)
    result = apply_hard_filters(j, analysis(), profile)
    assert result.rejected and "Azerbaijan" in result.reject_reasons[0]


def test_remote_eligibility_from_country_list(profile):
    unknown = RemoteEligibility.unknown
    assert remote_eligibility(job(remote_work_eligibility=unknown, eligible_countries=["Azerbaijan"]), profile) == RemoteEligibility.eligible
    assert remote_eligibility(job(remote_work_eligibility=unknown, eligible_countries=["azerbaijan "]), profile) == RemoteEligibility.eligible
    assert remote_eligibility(job(remote_work_eligibility=unknown, eligible_countries=["Worldwide"]), profile) == RemoteEligibility.eligible
    assert remote_eligibility(job(remote_work_eligibility=unknown, eligible_countries=["USA", "Canada"]), profile) == RemoteEligibility.not_eligible
    assert remote_eligibility(job(remote_work_eligibility=unknown), profile) == RemoteEligibility.unknown


def test_explicit_eligibility_wins_over_country_list(profile):
    j = job(remote_work_eligibility=RemoteEligibility.eligible, eligible_countries=["USA"])
    assert remote_eligibility(j, profile) == RemoteEligibility.eligible


def test_remote_unknown_eligibility_needs_review_not_reject(profile):
    j = job(remote_work_eligibility=RemoteEligibility.unknown, location_restrictions="EU timezone preferred")
    result = apply_hard_filters(j, analysis(), profile)
    assert not result.rejected
    assert len(result.review_reasons) == 2 and "EU timezone" in result.review_reasons[1]


def test_onsite_abroad_needs_review(profile):
    j = job(remote_type=RemoteType.onsite, country="Germany")
    result = apply_hard_filters(j, analysis(), profile)
    assert not result.rejected and "Germany" in result.review_reasons[0]


def test_onsite_in_home_country_is_clean(profile):
    j = job(remote_type=RemoteType.onsite, country="Azerbaijan", location="Baku")
    result = apply_hard_filters(j, analysis(), profile)
    assert not result.rejected and not result.review_reasons


def test_nothing_known_about_location_needs_review(profile):
    j = job(remote_type=RemoteType.unknown)
    assert apply_hard_filters(j, analysis(), profile).review_reasons == ["Location and work type are not stated"]


def test_several_reasons_are_all_listed(profile):
    j = job(country="India")
    result = apply_hard_filters(j, analysis(seniority=Seniority.senior, min_years=5), profile)
    assert len(result.reject_reasons) == 3
