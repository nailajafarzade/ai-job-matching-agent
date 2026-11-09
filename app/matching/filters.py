"""Hard filters. They run first and are separate from the scores.

A filter either rejects a job (with a reason) or flags it for manual
review (when something important is not known). Nothing is rejected
because of missing information.
"""
import re
from dataclasses import dataclass, field

from app.matching.types import JobFacts
from app.profile.loader import Profile
from app.schemas.analysis import AnalysisResult
from app.schemas.enums import RemoteEligibility, RemoteType

_OPEN_TO_ALL = {"worldwide", "global", "anywhere", "international", "any country", "all countries"}


@dataclass
class FilterResult:
    reject_reasons: list[str] = field(default_factory=list)
    review_reasons: list[str] = field(default_factory=list)

    @property
    def rejected(self) -> bool:
        return bool(self.reject_reasons)


def _mentions(text: str | None, word: str) -> bool:
    """Whole-word, case-insensitive. 'India' does not match 'Indiana'."""
    if not text:
        return False
    return re.search(rf"(?<![A-Za-z]){re.escape(word)}(?![A-Za-z])", text, re.IGNORECASE) is not None


def remote_eligibility(job: JobFacts, profile: Profile) -> RemoteEligibility:
    """Can I (from the home country) apply to this remote job?

    An explicit value wins. Otherwise the list of eligible countries decides.
    No information means unknown.
    """
    if job.remote_work_eligibility != RemoteEligibility.unknown:
        return job.remote_work_eligibility
    countries = {c.strip().lower() for c in job.eligible_countries if c.strip()}
    if not countries:
        return RemoteEligibility.unknown
    if profile.home_country.lower() in countries or countries & _OPEN_TO_ALL:
        return RemoteEligibility.eligible
    return RemoteEligibility.not_eligible


def apply_hard_filters(job: JobFacts, analysis: AnalysisResult, profile: Profile) -> FilterResult:
    result = FilterResult()

    # 1. Seniority
    if analysis.seniority.value in profile.reject_seniority:
        result.reject_reasons.append(f"Seniority is '{analysis.seniority.value}'")

    # 2. Required years of experience
    if analysis.min_years is not None and analysis.min_years > profile.max_years_required:
        result.reject_reasons.append(
            f"Requires {analysis.min_years} years of experience (limit is {profile.max_years_required})"
        )

    # 3. Excluded countries
    for country in profile.excluded_job_countries:
        if _mentions(job.country, country) or _mentions(job.location, country):
            result.reject_reasons.append(f"Job is in {country}")

    # 4. Remote and location
    is_remote = job.remote_type == RemoteType.remote
    if is_remote:
        if not profile.remote_ok:
            result.reject_reasons.append("Remote jobs are turned off in the profile")
        elif profile.require_country_eligibility:
            eligibility = remote_eligibility(job, profile)
            if eligibility == RemoteEligibility.not_eligible:
                result.reject_reasons.append(
                    f"Remote job does not accept applicants from {profile.home_country}"
                )
            elif eligibility == RemoteEligibility.unknown:
                result.review_reasons.append(
                    f"Remote job: it is not stated if applicants from {profile.home_country} are accepted"
                )
                if job.location_restrictions:
                    result.review_reasons.append(f"Location restrictions: {job.location_restrictions}")
    else:
        country = (job.country or "").strip()
        if country and country.lower() != profile.home_country.lower():
            result.review_reasons.append(
                f"Job is in {country} and is not clearly remote: check if hiring from "
                f"{profile.home_country} is possible"
            )
        elif not country and not job.location and job.remote_type == RemoteType.unknown:
            result.review_reasons.append("Location and work type are not stated")

    return result
