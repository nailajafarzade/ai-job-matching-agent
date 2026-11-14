"""Find application addresses only when the job post clearly invites contact."""
import re


_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_BLOCKED_PREFIXES = (
    "support@", "info@", "press@", "privacy@", "noreply@", "no-reply@", "legal@", "billing@",
)
_APPLY_WORDING = re.compile(
    r"\b(?:apply|send\s+(?:your\s+)?(?:cv|resume|résumé)|"
    r"email\s+(?:us\s+)?at|(?:cv|resume|résumé)\s+to)\b",
    re.IGNORECASE,
)
_EXCLUDED_CONTEXT = re.compile(r"\babout\s+us\b|contact\s+for\s+press", re.IGNORECASE)


def find_apply_email(text: str) -> str | None:
    """Return one unambiguous, non-service email tied to application wording."""
    lines = text.splitlines()
    candidates: dict[str, str] = {}
    for index, line in enumerate(lines):
        emails = _EMAIL.findall(line)
        if not emails:
            continue
        previous = lines[index - 1] if index > 0 else ""
        context = f"{previous} {line}"
        if _EXCLUDED_CONTEXT.search(context) or not _APPLY_WORDING.search(context):
            continue
        for email in emails:
            if email.lower().startswith(_BLOCKED_PREFIXES):
                continue
            candidates.setdefault(email.lower(), email)
    return next(iter(candidates.values())) if len(candidates) == 1 else None
