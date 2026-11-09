"""Matcher: puts filters and the three scores together into one decision.

Order of work:
1. Hard filters. If a job is rejected, we stop (no scores, no embeddings).
2. Skill score, semantic score, title score.
3. Final score = weighted sum. If the job names no known skill, the skill
   part is left out and the other weights are scaled to sum to 1.
4. Decision: rejected > below_threshold > needs_review > queued.
"""
from app.analysis.sections import split_into_segments
from app.analysis.vocabulary import SkillVocabulary
from app.config import MATCHER_VERSION, MAX_JOB_TEXT_CHARS, MIN_SCORE_TO_QUEUE, WEIGHTS
from app.matching.embeddings import Embedder
from app.matching.filters import apply_hard_filters
from app.matching.skills_score import score_skills
from app.matching.similarity import ProfileIndex
from app.matching.types import JobFacts, MatchResult
from app.profile.loader import Profile
from app.schemas.analysis import AnalysisResult
from app.schemas.enums import MatchDecision


def build_job_text(job: JobFacts) -> str:
    """Title + the useful part of the description (no 'About us', no benefits)."""
    parts = [seg.text for seg in split_into_segments(job.description) if seg.kind != "ignore"]
    return (job.title + ". " + " ".join(parts))[:MAX_JOB_TEXT_CHARS]


class Matcher:
    def __init__(
        self,
        profile: Profile,
        vocabulary: SkillVocabulary,
        embedder: Embedder,
        weights: dict[str, float] = WEIGHTS,
        min_score: float = MIN_SCORE_TO_QUEUE,
    ):
        self.profile = profile
        self.vocabulary = vocabulary
        self.embedder = embedder
        self.weights = weights
        self.min_score = min_score
        self.index = ProfileIndex(profile, embedder)  # embeds my texts once

    def match(self, job: JobFacts, analysis: AnalysisResult) -> MatchResult:
        base = dict(
            profile_version=self.profile.version,
            matcher_version=MATCHER_VERSION,
            embedding_model=self.embedder.name,
        )

        filters = apply_hard_filters(job, analysis, self.profile)
        if filters.rejected:
            return MatchResult(
                decision=MatchDecision.rejected,
                reject_reasons=filters.reject_reasons,
                review_reasons=filters.review_reasons,
                explanation="Rejected: " + "; ".join(filters.reject_reasons) + ".",
                **base,
            )

        skills = score_skills(analysis, self.profile, self.vocabulary.weights)
        semantic = self.index.semantic(build_job_text(job))
        title = self.index.title(job.title)

        parts = {"skill": skills.score, "semantic": semantic.score, "title": title.score}
        used = {name: w for name, w in self.weights.items() if parts[name] is not None}
        total_weight = sum(used.values())
        weights = {name: round(w / total_weight, 4) for name, w in used.items()}
        final = round(sum(weights[name] * parts[name] for name in weights), 2)

        if final < self.min_score:
            decision = MatchDecision.below_threshold
        elif filters.review_reasons:
            decision = MatchDecision.needs_review
        else:
            decision = MatchDecision.queued

        return MatchResult(
            decision=decision,
            review_reasons=filters.review_reasons,
            final_score=final,
            skill_score=skills.score,
            semantic_score=semantic.score,
            title_score=title.score,
            matched_skills=skills.matched,
            studied_skills=skills.studied,
            missing_skills=skills.missing,
            weights=weights,
            explanation=self._explain(final, skills, semantic, title, weights, decision, filters.review_reasons),
            **base,
        )

    def _explain(self, final, skills, semantic, title, weights, decision, review_reasons) -> str:
        lines = []
        if skills.score is None:
            lines.append("Skills: the job names no known skill, so the skill score is not used.")
        else:
            lines.append(f"Skills {skills.score:.0f}/100.")
            if skills.matched:
                lines.append("I know: " + ", ".join(skills.matched) + ".")
            if skills.studied:
                lines.append("Studied only (half credit): " + ", ".join(skills.studied) + ".")
            if skills.missing:
                lines.append("Missing: " + ", ".join(skills.missing) + ".")
        lines.append(f"Semantic {semantic.score:.0f}/100 (closest to my '{semantic.closest}').")
        lines.append(f"Title {title.score:.0f}/100 (closest target role: {title.closest}).")
        weight_text = ", ".join(f"{name} {w:g}" for name, w in weights.items())
        lines.append(f"Final {final:.1f} with weights {weight_text}. Decision: {decision.value}.")
        if review_reasons:
            lines.append("Check by hand: " + "; ".join(review_reasons) + ".")
        return " ".join(lines)
