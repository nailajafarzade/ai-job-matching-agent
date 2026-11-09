"""Content hash used to find duplicate jobs."""
import hashlib
import re


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def compute_content_hash(company: str, title: str, description: str) -> str:
    """Same company + title + description gives the same hash.

    Case and extra spaces do not matter. The URL is not used, because the
    same job can have different links.
    """
    raw = "|".join(_normalize(part) for part in (company, title, description))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
