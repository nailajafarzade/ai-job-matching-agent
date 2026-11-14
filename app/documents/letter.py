"""Render a plain, profile-based cover letter."""
from pathlib import Path
from typing import Protocol

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.config import TEMPLATES_DIR
from app.documents.facts import ApplicationFacts
from app.profile.loader import Profile


class LetterWriter(Protocol):
    def write(self, job, facts: ApplicationFacts, profile: Profile) -> str: ...


class TemplateLetterWriter:
    def __init__(self, templates_dir: Path = TEMPLATES_DIR):
        self.environment = Environment(
            loader=FileSystemLoader(templates_dir),
            undefined=StrictUndefined,
            autoescape=False,
            trim_blocks=False,
            lstrip_blocks=True,
        )

    def write(self, job, facts: ApplicationFacts, profile: Profile) -> str:
        project = facts.best_project
        is_team_project = bool(project and project.note and "team project" in project.note.casefold())
        student_identity = "second-year IT student"
        if student_identity.casefold() not in profile.summary.casefold():
            raise ValueError("profile summary does not confirm the student's year and field")
        template = self.environment.get_template("cover_letter.md.j2")
        letter = template.render(
            company=job.company,
            title=job.title,
            hands_on_matches=facts.hands_on_matches,
            studied_matches=facts.studied_matches,
            project=project,
            is_team_project=is_team_project,
            candidate_sentence=f"I am a {student_identity}.",
        )
        return "\n".join(line.strip() for line in letter.splitlines() if line.strip())
