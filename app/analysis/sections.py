"""Split a job text into sentences and tag each one:

  required : counts as a requirement (default)
  nice     : nice to have / bonus / preferred
  ignore   : about the company, benefits, perks

The tag comes from headings ("Nice to have:") and from words inside a
sentence ("Docker is a plus").
"""
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Segment:
    text: str
    kind: str  # "required" | "nice" | "ignore"


_HEADINGS: dict[str, list[str]] = {
    "nice": [
        "nice to have", "nice-to-have", "good to have", "bonus points", "bonus",
        "preferred qualifications", "preferred skills", "preferred", "advantages",
        "desirable", "optional", "pluses", "a plus", "extra points",
    ],
    "required": [
        "requirements", "required skills", "required qualifications", "required",
        "must have", "must-have", "qualifications", "what you need",
        "what we expect", "what we're looking for", "you have", "you will need",
        "your profile", "who you are", "about you", "skills and experience",
        "skills", "minimum qualifications", "mandatory", "technical skills",
        "tech stack", "responsibilities", "key responsibilities", "what you'll do",
        "what you will do", "your role", "duties",
    ],
    "ignore": [
        "about us", "about the company", "company overview", "benefits",
        "what we offer", "we offer", "perks", "why join us", "why join",
        "our culture", "equal opportunity",
    ],
}

_ALL = sorted(
    ((phrase, kind) for kind, phrases in _HEADINGS.items() for phrase in phrases),
    key=lambda item: -len(item[0]),
)
_KIND_OF = {phrase: kind for phrase, kind in _ALL}

_HEADING = re.compile(
    r"^(?P<phrase>" + "|".join(re.escape(p) for p, _ in _ALL) + r")"
    r"(?:\s+(?:skills|qualifications|requirements|technologies|experience))?"
    r"\s*(?P<sep>[:\-–—])?\s*(?P<rest>.*)$",
    re.IGNORECASE,
)
_BULLET = re.compile(r"^\s*(?:[-*•>#]+|\d+[.)])\s*")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?;])\s+")
_INLINE_NICE = re.compile(
    r"\b(?:is|are|would be|will be)\s+(?:a\s+)?(?:big\s+)?(?:plus|bonus|advantage|nice)\b"
    r"|\(\s*(?:a\s+)?(?:plus|bonus|nice to have)\s*\)"
    r"|\bnice[- ]to[- ]have\b|\bbonus\b|\bpreferred\b|\bpreferably\b"
    r"|\ban advantage\b|\ba plus\b|\bdesirable\b",
    re.IGNORECASE,
)


def split_into_segments(text: str) -> list[Segment]:
    segments: list[Segment] = []
    section = "required"
    for raw in text.replace("’", "'").splitlines():
        line = _BULLET.sub("", raw).strip()
        if not line:
            continue

        rest = line
        heading = _HEADING.match(line)
        # A heading has a separator ("Nice to have: ...") or nothing after it.
        if heading and (heading.group("sep") or not heading.group("rest")):
            section = _KIND_OF[heading.group("phrase").lower()]
            rest = heading.group("rest").strip()
            if not rest:
                continue

        for sentence in _SENTENCE_SPLIT.split(rest):
            sentence = sentence.strip()
            if not sentence:
                continue
            kind = section
            if section != "ignore" and _INLINE_NICE.search(sentence):
                kind = "nice"
            segments.append(Segment(sentence, kind))
    return segments
