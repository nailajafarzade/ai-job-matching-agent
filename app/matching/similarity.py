"""Semantic score and title score, both from embeddings.

ProfileIndex embeds my texts and target roles once. Each job then needs
only one or two embeddings.
"""
from dataclasses import dataclass

import numpy as np

from app.config import (
    ROLE_PRIORITY_FACTOR,
    SEMANTIC_CEIL,
    SEMANTIC_FLOOR,
    TITLE_CEIL,
    TITLE_FLOOR,
)
from app.matching.embeddings import Embedder
from app.profile.loader import Profile


def scale(value: float, floor: float, ceil: float) -> float:
    """Straight line from floor (0) to ceil (100), cut at both ends."""
    if ceil <= floor:
        raise ValueError("ceil must be bigger than floor")
    return round(100 * min(1.0, max(0.0, (value - floor) / (ceil - floor))), 2)


@dataclass
class ScoreWithReason:
    score: float
    closest: str  # the profile text or target role that was most similar
    raw_similarity: float


class ProfileIndex:
    def __init__(self, profile: Profile, embedder: Embedder):
        self.profile = profile
        self.embedder = embedder
        self.text_vectors = embedder.embed([t.text for t in profile.texts])
        self.role_vectors = embedder.embed([r.title for r in profile.target_roles])

    def semantic(self, job_text: str) -> ScoreWithReason:
        """Best match between the job text and any of my texts."""
        vector = self.embedder.embed([job_text])[0]
        sims = self.text_vectors @ vector
        best = int(np.argmax(sims))
        return ScoreWithReason(
            score=scale(float(sims[best]), SEMANTIC_FLOOR, SEMANTIC_CEIL),
            closest=self.profile.texts[best].label,
            raw_similarity=round(float(sims[best]), 4),
        )

    def title(self, job_title: str) -> ScoreWithReason:
        """Best match between the job title and my target roles.

        Less wanted roles are scaled down by their priority.
        """
        vector = self.embedder.embed([job_title])[0]
        sims = self.role_vectors @ vector
        best_score, best_index = -1.0, 0
        for i, role in enumerate(self.profile.target_roles):
            score = scale(float(sims[i]), TITLE_FLOOR, TITLE_CEIL) * ROLE_PRIORITY_FACTOR[role.priority]
            if score > best_score:
                best_score, best_index = score, i
        return ScoreWithReason(
            score=round(best_score, 2),
            closest=self.profile.target_roles[best_index].title,
            raw_similarity=round(float(sims[best_index]), 4),
        )
