"""Find skills from skills.yaml inside a text.

Rules:
- Only the canonical name and its true synonyms count as a mention.
  `related` skills are never matched here.
- The longest name wins: "Spring Boot" is one skill, not "Spring" + "Boot",
  and "Docker Compose" does not also count as "Docker".
- Whole words only: "Java" is not found inside "JavaScript".
"""
import re
from functools import lru_cache
from pathlib import Path

import yaml

from app.config import SKILLS_PATH

# Ordinary English words that are also skill names. They count only when
# written in the listed form ("REST", not "the rest of the team").
CASE_SENSITIVE_FORMS: dict[str, list[str]] = {
    "rest": ["REST"],
    "spring": ["Spring"],
    "react": ["React"],
    "node": ["Node"],
    "flask": ["Flask"],
    "ml": ["ML"],
}

_BEFORE = r"(?<![A-Za-z0-9_])"
_AFTER = r"(?![A-Za-z0-9_])"
_YEAR_AFTER = re.compile(r"\s+(?:19|20)\d\d\b")  # "Spring 2026 internship" is a season


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _term_pattern(term: str) -> str:
    return r"\s+".join(re.escape(part) for part in term.split())


class SkillVocabulary:
    def __init__(self, skills: list[dict]):
        self.canonical_names: set[str] = {s["canonical"] for s in skills}
        self.weights: dict[str, int] = {s["canonical"]: s.get("weight", 1) for s in skills}
        self._term_to_canonical: dict[str, str] = {}
        for skill in skills:
            canonical = skill["canonical"]
            for term in [canonical, *skill.get("synonyms", [])]:
                self._term_to_canonical[_normalize(term)] = canonical

        alternatives: list[tuple[int, str]] = []
        for term in self._term_to_canonical:
            if term in CASE_SENSITIVE_FORMS:
                for form in CASE_SENSITIVE_FORMS[term]:
                    alternatives.append((len(term), re.escape(form)))
            else:
                alternatives.append((len(term), f"(?i:{_term_pattern(term)})"))
        alternatives.sort(key=lambda item: -item[0])  # longest name first
        body = "|".join(pattern for _, pattern in alternatives)
        self._regex = re.compile(f"{_BEFORE}(?:{body}){_AFTER}")

    @classmethod
    def from_file(cls, path: Path = SKILLS_PATH) -> "SkillVocabulary":
        with open(path, encoding="utf-8") as f:
            return cls(yaml.safe_load(f)["skills"])

    def find(self, text: str) -> list[str]:
        """Canonical skill names in the order they first appear, no duplicates."""
        found: list[str] = []
        for match in self._regex.finditer(text):
            canonical = self._term_to_canonical[_normalize(match.group())]
            if canonical == "Spring Framework" and _YEAR_AFTER.match(text, match.end()):
                continue
            if canonical not in found:
                found.append(canonical)
        return found


@lru_cache(maxsize=1)
def get_vocabulary() -> SkillVocabulary:
    return SkillVocabulary.from_file()
