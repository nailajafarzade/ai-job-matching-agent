"""Select profile facts that may safely appear in an application."""
from dataclasses import dataclass

from app.analysis.vocabulary import get_vocabulary
from app.profile.loader import Profile


@dataclass(frozen=True)
class ProjectFact:
    name: str
    role: str | None
    tech_confirmed: list[str]
    note: str | None


@dataclass(frozen=True)
class ApplicationFacts:
    hands_on_matches: list[str]
    studied_matches: list[str]
    missing: list[str]
    best_project: ProjectFact | None


def build_facts(job, analysis, profile: Profile) -> ApplicationFacts:
    del job  # The title and company are used by the letter writer, not as profile facts.
    vocabulary = get_vocabulary()
    job_skills = list(dict.fromkeys(analysis.required_skills + analysis.nice_to_have_skills))
    hands_on = [skill for skill in job_skills if profile.level_of(skill) == "hands_on"]
    studied = [skill for skill in job_skills if profile.level_of(skill) == "studied"]
    missing = [skill for skill in job_skills if profile.level_of(skill) is None]
    hands_on.sort(key=lambda skill: -vocabulary.weights.get(skill, 1))
    studied.sort(key=lambda skill: -vocabulary.weights.get(skill, 1))

    best_project = None
    if profile.projects:
        project = max(
            profile.projects,
            key=lambda item: sum(skill in job_skills for skill in item.tech_confirmed),
        )
        best_project = ProjectFact(project.name, project.role, project.tech_confirmed, project.note)

    return ApplicationFacts(hands_on[:5], studied[:3], missing, best_project)
