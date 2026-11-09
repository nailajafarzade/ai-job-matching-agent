"""Fixed value lists shared by the database and the schemas."""
from enum import Enum


class Seniority(str, Enum):
    intern = "intern"
    junior = "junior"
    mid = "mid"
    senior = "senior"
    lead = "lead"
    principal = "principal"
    staff = "staff"
    manager = "manager"
    unknown = "unknown"


class RemoteType(str, Enum):
    onsite = "onsite"
    hybrid = "hybrid"
    remote = "remote"
    unknown = "unknown"


class RemoteEligibility(str, Enum):
    """Can I (from Azerbaijan) apply to this remote job?"""
    eligible = "eligible"
    not_eligible = "not_eligible"
    unknown = "unknown"  # flagged for manual review, never rejected silently


class JobStatus(str, Enum):
    """Where the job is in the stage 1 pipeline."""
    new = "new"
    analyzed = "analyzed"
    matched = "matched"


class MatchDecision(str, Enum):
    rejected = "rejected"              # hard filter said no
    needs_review = "needs_review"      # something is unknown (e.g. remote eligibility)
    below_threshold = "below_threshold"  # scored, but under MIN_SCORE_TO_QUEUE
    queued = "queued"                  # good enough to prepare an application
