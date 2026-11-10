"""Build the job pipeline with the current profile and embedding model."""
from pathlib import Path

from app.analysis.analyzer import get_analyzer
from app.analysis.vocabulary import get_vocabulary
from app.config import MIN_SCORE_TO_QUEUE
from app.matching.embeddings import Embedder
from app.matching.scorer import Matcher
from app.profile.loader import load_profile
from app.services.pipeline import JobPipeline


def build_pipeline(
    profile_path: Path,
    embedder: Embedder,
    min_score: float | None = None,
) -> JobPipeline:
    vocabulary = get_vocabulary()
    profile = load_profile(profile_path, vocabulary)
    matcher = Matcher(
        profile,
        vocabulary,
        embedder,
        min_score=MIN_SCORE_TO_QUEUE if min_score is None else min_score,
    )
    return JobPipeline(get_analyzer(), matcher)
