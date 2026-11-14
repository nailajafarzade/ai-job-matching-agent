"""Check a generated letter for unsupported claims and placeholders."""
from typing import Literal
import re

from pydantic import BaseModel

from app.analysis.vocabulary import SkillVocabulary
from app.config import MAX_LETTER_WORDS
from app.profile.loader import Profile


class Issue(BaseModel):
    level: Literal["error", "warning"]
    message: str


def _sentences(text: str) -> list[str]:
    return [part for part in re.split(r"(?<=[.!?])\s+|\n+", text) if part.strip()]


def _job_decision(job) -> str | None:
    direct = getattr(job, "decision", None) or getattr(job, "match_decision", None)
    if direct is not None:
        return getattr(direct, "value", direct)
    matches = getattr(job, "matches", None) or []
    if matches:
        decision = matches[-1].decision
        return getattr(decision, "value", decision)
    return None


def review_letter(text: str, job, profile: Profile, vocabulary: SkillVocabulary) -> list[Issue]:
    issues = []
    found_skills = vocabulary.find(text)
    for skill in found_skills:
        level = profile.level_of(skill)
        if level is None:
            issues.append(Issue(level="error", message=f"Letter names a skill not in the profile: {skill}."))
        elif level == "studied":
            outside_learning = any(
                skill in vocabulary.find(sentence)
                and re.match(r"\s*I am also learning\b", sentence, re.IGNORECASE) is None
                for sentence in _sentences(text)
            )
            if outside_learning:
                issues.append(Issue(level="error", message=f"Studied skill '{skill}' appears outside the learning sentence."))

    if re.search(r"\b\d+\s*\+?\s+years?\b", text, re.IGNORECASE):
        issues.append(Issue(level="error", message="Letter contains an unverified years-of-experience claim."))
    if "{{" in text or "}}" in text or re.search(r"\bTODO\b|(?<!\w)None(?!\w)", text):
        issues.append(Issue(level="error", message="Letter contains an unfilled placeholder."))
    if job.company.casefold() not in text.casefold():
        issues.append(Issue(level="error", message="Letter does not name the company."))
    if job.title.casefold() not in text.casefold():
        issues.append(Issue(level="error", message="Letter does not name the job title."))

    if len(text.split()) > MAX_LETTER_WORDS:
        issues.append(Issue(level="warning", message=f"Letter is longer than {MAX_LETTER_WORDS} words."))
    if _job_decision(job) == "needs_review":
        issues.append(Issue(level="warning", message="Job match needs manual review."))
    return issues
