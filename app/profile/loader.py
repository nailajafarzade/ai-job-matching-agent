"""Load and check profile.yaml.

The profile is the only source of truth about me. The loader refuses a
profile with a skill that is not in the vocabulary or a level that is not
allowed, so a typo cannot silently change a match.
"""
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.analysis.vocabulary import SkillVocabulary, get_vocabulary
from app.config import PROFILE_PATH

LEVELS = ("hands_on", "studied")
PRIORITIES = ("high", "medium", "secondary")


@dataclass(frozen=True)
class TargetRole:
    title: str
    priority: str


@dataclass(frozen=True)
class ProfileText:
    """A short true text about me. Used for the semantic score."""
    label: str
    text: str


@dataclass(frozen=True)
class ProfileProject:
    name: str
    role: str | None
    text: str
    tech_confirmed: list[str]
    note: str | None = None


@dataclass(frozen=True)
class Profile:
    version: int
    skills: dict[str, str]                      # canonical name -> level
    target_roles: list[TargetRole]
    texts: list[ProfileText]
    max_years_required: int
    reject_seniority: list[str]
    home_country: str
    excluded_job_countries: list[str]
    remote_ok: bool
    require_country_eligibility: bool
    preferred_locations: list[str] = field(default_factory=list)
    summary: str = ""
    projects: list[ProfileProject] = field(default_factory=list)

    def level_of(self, skill: str) -> str | None:
        return self.skills.get(skill)


def parse_profile(data: dict, vocabulary: SkillVocabulary) -> Profile:
    skills: dict[str, str] = {}
    for item in data["skills"]:
        name, level = item["name"], item["level"]
        if level not in LEVELS:
            raise ValueError(f"Skill '{name}' has level '{level}'. Allowed: {LEVELS}")
        if name not in vocabulary.canonical_names:
            raise ValueError(f"Profile skill '{name}' is not in skills.yaml")
        if name in skills:
            raise ValueError(f"Profile skill '{name}' is listed twice")
        skills[name] = level

    roles = []
    for item in data["target_roles"]:
        if item["priority"] not in PRIORITIES:
            raise ValueError(f"Role '{item['title']}' has priority '{item['priority']}'. Allowed: {PRIORITIES}")
        roles.append(TargetRole(item["title"], item["priority"]))
    if not roles:
        raise ValueError("target_roles is empty")

    summary = " ".join(data["summary"].split())
    projects = [
        ProfileProject(
            name=project["name"],
            role=project.get("role"),
            text=" ".join(project["text"].split()),
            tech_confirmed=list(project.get("tech_confirmed", [])),
            note=project.get("note"),
        )
        for project in data.get("projects", [])
    ]
    texts = [ProfileText("summary", summary)]
    texts.extend(ProfileText(project.name, project.text) for project in projects)
    hands_on = [name for name, level in skills.items() if level == "hands_on"]
    texts.append(ProfileText("skills", "Skills: " + ", ".join(hands_on) + "."))

    prefs = data["preferences"]
    remote = prefs.get("remote", {})
    return Profile(
        version=int(data["version"]),
        skills=skills,
        target_roles=roles,
        texts=texts,
        max_years_required=int(prefs["max_years_required"]),
        reject_seniority=[s.lower() for s in prefs["reject_seniority"]],
        home_country=prefs["home_country"],
        excluded_job_countries=list(prefs.get("excluded_job_countries", [])),
        remote_ok=bool(remote.get("ok", True)),
        require_country_eligibility=bool(remote.get("require_country_eligibility", True)),
        preferred_locations=list(prefs.get("preferred_locations", [])),
        summary=summary,
        projects=projects,
    )


def load_profile(path: Path = PROFILE_PATH, vocabulary: SkillVocabulary | None = None) -> Profile:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return parse_profile(data, vocabulary or get_vocabulary())
