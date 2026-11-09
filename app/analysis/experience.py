"""Find the minimum years of experience a job asks for."""
import re

from app.analysis.sections import Segment

_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
_NUMBER = r"(\d{1,2}|" + "|".join(_WORDS) + r")"
# "1-2 years", "2 to 3 years", "3+ years", "at least two years"
_YEARS = re.compile(
    rf"(?<![\d.]){_NUMBER}\s*\+?\s*(?:(?:-|–|to)\s*{_NUMBER}\s*\+?\s*)?(?:years?|yrs?)\b(?P<after>[^.;]{{0,12}})",
    re.IGNORECASE,
)
_UPPER_LIMIT = re.compile(r"(?:less than|up to|under|fewer than|no more than|maximum|max)\s*$", re.IGNORECASE)
_EXPERIENCE_WORDS = re.compile(r"experience|exp\.|commercial|professional|hands-on", re.IGNORECASE)
_NO_EXPERIENCE = re.compile(
    r"\bno\s+(?:prior\s+|previous\s+|relevant\s+|professional\s+|commercial\s+)?experience\b"
    r"|\bwithout\s+(?:prior\s+)?experience\b|\bexperience\s+(?:is\s+)?not\s+required\b",
    re.IGNORECASE,
)


def _to_int(token: str) -> int:
    return _WORDS[token.lower()] if token.lower() in _WORDS else int(token)


def extract_min_years(segments: list[Segment]) -> int | None:
    """The biggest requirement found in 'required' sentences, or None.

    A range uses its lower bound ("1-2 years" -> 1). Only sentences that talk
    about experience count, so "founded 10 years ago" is ignored.
    Returns 0 for "no experience required".
    """
    found: list[int] = []
    no_experience = False
    for segment in segments:
        if segment.kind == "ignore":
            continue
        text = segment.text
        # "No experience required, but 2 years is preferred" is a nice-type
        # sentence, but its first part is still a clear statement.
        if _NO_EXPERIENCE.search(text):
            no_experience = True
        if segment.kind != "required":
            continue
        if not _EXPERIENCE_WORDS.search(text):
            continue
        for match in _YEARS.finditer(text):
            if _UPPER_LIMIT.search(text[: match.start()]):
                continue
            if re.match(r"\s*old\b", match.group("after") or "", re.IGNORECASE):
                continue
            found.append(_to_int(match.group(1)))
    if found:
        return max(found)
    return 0 if no_experience else None
