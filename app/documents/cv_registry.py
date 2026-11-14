"""Load and validate the owner's CV registry."""
from dataclasses import dataclass
from pathlib import Path

import yaml

from app.analysis.vocabulary import SkillVocabulary
from app.config import BASE_DIR, CV_REGISTRY_PATH
from app.profile.loader import Profile


@dataclass(frozen=True)
class CvEntry:
    id: str
    file: Path
    target_roles: list[str]
    emphasis_skills: list[str]


@dataclass(frozen=True)
class CvRegistry:
    entries: list[CvEntry]
    warnings: list[str]


def load_cv_registry(
    path: Path = CV_REGISTRY_PATH,
    profile: Profile | None = None,
    vocabulary: SkillVocabulary | None = None,
) -> CvRegistry:
    if profile is None or vocabulary is None:
        raise ValueError("profile and vocabulary are required to validate the CV registry")

    with open(path, encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    entries = []
    warnings = []
    seen_ids = set()
    profile_roles = {role.title for role in profile.target_roles}
    for item in data.get("cvs", []):
        cv_id = item.get("id")
        if not isinstance(cv_id, str) or not cv_id.strip():
            raise ValueError("CV ids must be non-empty strings")
        if cv_id in seen_ids:
            raise ValueError(f"CV id '{cv_id}' is listed twice")
        seen_ids.add(cv_id)

        emphasis_skills = list(item.get("emphasis_skills", []))
        for skill in emphasis_skills:
            if skill not in vocabulary.canonical_names:
                raise ValueError(f"CV '{cv_id}' emphasis skill '{skill}' is not in skills.yaml")
            if skill not in profile.skills:
                raise ValueError(f"CV '{cv_id}' emphasis skill '{skill}' is not in profile.yaml")

        target_roles = list(item.get("target_roles", []))
        for role in target_roles:
            if role not in profile_roles:
                raise ValueError(f"CV '{cv_id}' target role '{role}' is not in profile.yaml")

        cv_file = Path(item["file"])
        if not cv_file.is_absolute():
            cv_file = BASE_DIR / cv_file
        if not cv_file.is_file():
            warnings.append(f"CV file is missing: {cv_file}")
        entries.append(CvEntry(cv_id, cv_file, target_roles, emphasis_skills))

    if not entries:
        raise ValueError("CV registry must contain at least one CV")
    return CvRegistry(entries, warnings)
