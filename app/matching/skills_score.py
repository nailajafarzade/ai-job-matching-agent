"""Skill score: how much of what the job asks do I really have?

Every skill the job asks for has a weight (from skills.yaml).
- required skill: full weight
- nice-to-have skill: weight * NICE_TO_HAVE_SKILL_FACTOR
- I know it hands-on: full credit
- I only studied it: STUDIED_SKILL_CREDIT
- not in my profile: no credit, and it goes to missing_skills

Only the exact skill counts. Related skills (Jenkins for CI/CD, Dockerfile
for Docker, ...) give no credit.
"""
from dataclasses import dataclass, field

from app.config import NICE_TO_HAVE_SKILL_FACTOR, REQUIRED_SKILL_FACTOR, STUDIED_SKILL_CREDIT
from app.profile.loader import Profile
from app.schemas.analysis import AnalysisResult


@dataclass
class SkillScore:
    score: float | None            # 0-100, None if the job names no known skill
    matched: list[str] = field(default_factory=list)   # hands_on
    studied: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


def score_skills(analysis: AnalysisResult, profile: Profile, weights: dict[str, int]) -> SkillScore:
    asked: list[tuple[str, float]] = [(s, REQUIRED_SKILL_FACTOR) for s in analysis.required_skills]
    asked += [(s, NICE_TO_HAVE_SKILL_FACTOR) for s in analysis.nice_to_have_skills]
    if not asked:
        return SkillScore(score=None)

    result = SkillScore(score=0.0)
    total = earned = 0.0
    for skill, factor in asked:
        weight = weights.get(skill, 1) * factor
        level = profile.level_of(skill)
        if level == "hands_on":
            credit = 1.0
            result.matched.append(skill)
        elif level == "studied":
            credit = STUDIED_SKILL_CREDIT
            result.studied.append(skill)
        else:
            credit = 0.0
            result.missing.append(skill)
        total += weight
        earned += weight * credit

    result.score = round(100 * earned / total, 2)
    return result
