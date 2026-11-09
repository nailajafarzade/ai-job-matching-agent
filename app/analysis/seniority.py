"""Find the seniority level of a job.

The title decides. The description is used only for clear phrases, because
sentences like "mentor junior developers" or "work with senior engineers"
say nothing about the level of this job.
"""
import re

from app.schemas.enums import Seniority

# Order matters: the first match wins ("Engineering Manager" before "Engineer").
_TITLE_PATTERNS: list[tuple[Seniority, re.Pattern]] = [
    (Seniority.manager, re.compile(r"\b(?:manager|head of|director|vp|vice president)\b", re.I)),
    (Seniority.principal, re.compile(r"\bprincipal\b", re.I)),
    (Seniority.staff, re.compile(r"\bstaff\b", re.I)),
    (Seniority.lead, re.compile(r"\b(?:lead|team lead|tech lead|technical lead)\b", re.I)),
    (Seniority.senior, re.compile(r"\b(?:senior|sr)\b", re.I)),
    (Seniority.mid, re.compile(r"\b(?:mid|middle|intermediate|mid-level)\b", re.I)),
    (Seniority.junior, re.compile(r"\b(?:junior|jr|entry[- ]level|graduate)\b", re.I)),
    (Seniority.intern, re.compile(r"\b(?:intern|interns|internship|trainee|apprentice)\b", re.I)),
]
_ENTRY_LEVEL = re.compile(r"\bentry[- ]level\b", re.I)
_LOOKING_FOR = re.compile(
    r"\b(?:we are looking for|we're looking for|seeking|hiring)\s+(?:a|an)\s+(senior|junior|lead|principal|staff)\b",
    re.I,
)


def detect_seniority(title: str, description: str = "") -> Seniority:
    for level, pattern in _TITLE_PATTERNS:
        if pattern.search(title):
            return level
    if _ENTRY_LEVEL.search(description):
        return Seniority.junior
    match = _LOOKING_FOR.search(description)
    if match:
        return Seniority(match.group(1).lower())
    return Seniority.unknown
