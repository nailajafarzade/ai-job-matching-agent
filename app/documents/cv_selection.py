"""Choose the most relevant registered CV for a job."""
from dataclasses import dataclass
import re

from app.analysis.vocabulary import SkillVocabulary
from app.config import CV_TITLE_BONUS
from app.documents.cv_registry import CvRegistry

_GENERIC_TITLE_WORDS = {"developer", "engineer", "intern", "junior", "senior", "software", "role", "position"}


@dataclass(frozen=True)
class CvChoice:
    cv_id: str
    score: float
    reason: str


def _title_words(title: str) -> set[str]:
    words = set(re.findall(r"[a-z0-9+#]+", title.casefold()))
    return words - _GENERIC_TITLE_WORDS


def _title_is_close(job_title: str, target_role: str) -> bool:
    job_words = _title_words(job_title)
    role_words = _title_words(target_role)
    if not job_words or not role_words:
        return False
    return len(job_words & role_words) / len(job_words | role_words) >= 0.5


def select_cv(job, analysis, registry: CvRegistry, vocabulary: SkillVocabulary) -> CvChoice:
    scored = []
    for order, cv in enumerate(registry.entries):
        matched = [skill for skill in analysis.required_skills if skill in cv.emphasis_skills]
        score = sum(vocabulary.weights.get(skill, 1) for skill in matched)
        matching_roles = [role for role in cv.target_roles if _title_is_close(job.title, role)]
        if matching_roles:
            score += CV_TITLE_BONUS
        scored.append((score, -order, cv, matched, matching_roles))

    score, _, cv, matched, matching_roles = max(scored, key=lambda item: (item[0], item[1]))
    if score == 0:
        return CvChoice(cv.id, score, "No required-skill or title overlap; selected the first CV as a fallback.")

    reasons = []
    if matched:
        reasons.append("required skills: " + ", ".join(matched))
    if matching_roles:
        reasons.append("title is close to " + ", ".join(matching_roles))
    return CvChoice(cv.id, float(score), "Selected for " + " and ".join(reasons) + ".")
