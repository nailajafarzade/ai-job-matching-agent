"""Build the job pipeline with the current profile and embedding model."""
from dataclasses import dataclass
from pathlib import Path

from app.analysis.analyzer import get_analyzer
from app.analysis.vocabulary import SkillVocabulary, get_vocabulary
from app.config import CV_REGISTRY_PATH, MIN_SCORE_TO_QUEUE
from app.documents.cv_registry import CvRegistry, load_cv_registry
from app.documents.letter import LetterWriter, TemplateLetterWriter
from app.matching.embeddings import Embedder
from app.matching.scorer import Matcher
from app.profile.loader import Profile, load_profile
from app.services.pipeline import JobPipeline


@dataclass(frozen=True)
class DocumentServices:
    profile: Profile
    vocabulary: SkillVocabulary
    cv_registry: CvRegistry
    letter_writer: LetterWriter


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


def build_documents(profile: Profile, vocabulary: SkillVocabulary) -> DocumentServices:
    registry = load_cv_registry(CV_REGISTRY_PATH, profile, vocabulary)
    return DocumentServices(profile, vocabulary, registry, TemplateLetterWriter())
