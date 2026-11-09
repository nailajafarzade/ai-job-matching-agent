"""Job analyzer: job text in, AnalysisResult out. Plain rules, no model."""
from functools import lru_cache

from app.analysis.experience import extract_min_years
from app.analysis.seniority import detect_seniority
from app.analysis.sections import Segment, split_into_segments
from app.analysis.vocabulary import SkillVocabulary, get_vocabulary
from app.schemas.analysis import AnalysisResult


class JobAnalyzer:
    def __init__(self, vocabulary: SkillVocabulary):
        self.vocabulary = vocabulary

    def analyze(self, title: str, description: str) -> AnalysisResult:
        # Skills in the title count as required.
        segments = [Segment(title, "required"), *split_into_segments(description)]

        required: list[str] = []
        nice: list[str] = []
        for segment in segments:
            if segment.kind == "ignore":
                continue
            target = required if segment.kind == "required" else nice
            for skill in self.vocabulary.find(segment.text):
                if skill not in target:
                    target.append(skill)

        # A skill that is required anywhere is required.
        nice = [skill for skill in nice if skill not in required]

        return AnalysisResult(
            required_skills=required,
            nice_to_have_skills=nice,
            min_years=extract_min_years(segments),
            seniority=detect_seniority(title, description),
        )


@lru_cache(maxsize=1)
def get_analyzer() -> JobAnalyzer:
    return JobAnalyzer(get_vocabulary())
