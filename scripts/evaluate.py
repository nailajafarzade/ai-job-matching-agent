"""Report how the matcher performs on manually labeled job posts."""
import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

from app.analysis.analyzer import JobAnalyzer
from app.config import PROFILE_PATH
from app.matching.embeddings import get_embedder
from app.matching.scorer import Matcher
from app.matching.types import JobFacts, MatchResult
from app.schemas.enums import MatchDecision, RemoteType
from app.services.runtime import build_pipeline

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = PROJECT_ROOT / "data" / "labeled_jobs.csv"
EXPECTED_COLUMNS = {
    "title",
    "company",
    "description_file",
    "country",
    "remote_type",
    "eligible_countries",
    "label",
}


@dataclass(frozen=True)
class EvaluationRow:
    title: str
    decision: str
    final_score: float | None
    skill_score: float | None
    semantic_score: float | None
    title_score: float | None
    label: str


@dataclass(frozen=True)
class EvaluationSummary:
    apply_queued: int
    apply_needs_review: int
    skip_queued: int
    average_apply_score: float | None
    average_skip_score: float | None
    disagreements: list[EvaluationRow]


def read_jobs(csv_path: Path) -> list[tuple[JobFacts, str]]:
    """Read job facts and labels from the CSV and description files."""
    path = csv_path if csv_path.is_absolute() else PROJECT_ROOT / csv_path
    jobs_dir = (PROJECT_ROOT / "data" / "jobs").resolve()
    jobs = []
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        missing = EXPECTED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError("CSV is missing columns: " + ", ".join(sorted(missing)))
        for line_number, row in enumerate(reader, start=2):
            label = (row["label"] or "").strip().lower()
            if label not in {"apply", "skip"}:
                raise ValueError(f"Line {line_number}: label must be apply or skip")

            description_value = (row["description_file"] or "").strip()
            if not description_value:
                raise ValueError(f"Line {line_number}: description_file is empty")
            description_path = Path(description_value)
            if not description_path.is_absolute():
                description_path = PROJECT_ROOT / description_path
            description_path = description_path.resolve()
            if not description_path.is_relative_to(jobs_dir):
                raise ValueError(f"Line {line_number}: description_file must be inside data/jobs")

            remote_value = (row["remote_type"] or "").strip().lower() or RemoteType.unknown.value
            eligible_countries = [
                country.strip()
                for country in (row["eligible_countries"] or "").split(";")
                if country.strip()
            ]
            job = JobFacts(
                title=(row["title"] or "").strip(),
                description=description_path.read_text(encoding="utf-8"),
                country=(row["country"] or "").strip() or None,
                remote_type=RemoteType(remote_value),
                eligible_countries=eligible_countries,
            )
            jobs.append((job, label))
    return jobs


def evaluate_job(job: JobFacts, label: str, matcher: Matcher, analyzer: JobAnalyzer) -> EvaluationRow:
    """Analyze and match one job, then keep the scores for reporting."""
    analysis = analyzer.analyze(job.title, job.description)
    result: MatchResult = matcher.match(job, analysis)
    return EvaluationRow(
        title=job.title,
        decision=result.decision.value,
        final_score=result.final_score,
        skill_score=result.skill_score,
        semantic_score=result.semantic_score,
        title_score=result.title_score,
        label=label,
    )


def _average_score(rows: list[EvaluationRow], label: str) -> float | None:
    scores = []
    for row in rows:
        if row.label == label and row.final_score is not None:
            scores.append(row.final_score)
    return round(sum(scores) / len(scores), 2) if scores else None


def summarize(rows: list[EvaluationRow]) -> EvaluationSummary:
    """Count the requested outcomes and find clear label disagreements."""
    apply_queued = sum(row.label == "apply" and row.decision == MatchDecision.queued.value for row in rows)
    apply_needs_review = sum(
        row.label == "apply" and row.decision == MatchDecision.needs_review.value for row in rows
    )
    skip_queued = sum(row.label == "skip" and row.decision == MatchDecision.queued.value for row in rows)
    disagreements = [
        row
        for row in rows
        if (row.label == "apply" and row.decision in {"rejected", "below_threshold"})
        or (row.label == "skip" and row.decision == MatchDecision.queued.value)
    ]
    return EvaluationSummary(
        apply_queued=apply_queued,
        apply_needs_review=apply_needs_review,
        skip_queued=skip_queued,
        average_apply_score=_average_score(rows, "apply"),
        average_skip_score=_average_score(rows, "skip"),
        disagreements=disagreements,
    )


def _score_text(score: float | None) -> str:
    return "-" if score is None else f"{score:.1f}"


def print_report(rows: list[EvaluationRow], summary: EvaluationSummary) -> None:
    """Print scores, counts, averages and disagreements."""
    print(f"{'Title':42} {'Decision':16} {'Final':>7} {'Skill':>7} {'Semantic':>9} {'Title':>7} {'Label':>7}")
    print("-" * 102)
    for row in rows:
        print(
            f"{row.title[:42]:42} {row.decision:16} {_score_text(row.final_score):>7} "
            f"{_score_text(row.skill_score):>7} {_score_text(row.semantic_score):>9} "
            f"{_score_text(row.title_score):>7} {row.label:>7}"
        )

    apply_average = _score_text(summary.average_apply_score)
    skip_average = _score_text(summary.average_skip_score)
    print("\nCounts:")
    print(f"  apply jobs: queued={summary.apply_queued}, needs_review={summary.apply_needs_review}")
    print(f"  skip jobs: queued={summary.skip_queued}")
    print(f"  average final score: apply={apply_average}, skip={skip_average}")
    print("  disagreements:")
    if not summary.disagreements:
        print("    none")
    for row in summary.disagreements:
        print(f"    {row.title}: label={row.label}, decision={row.decision}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", nargs="?", type=Path, default=DEFAULT_CSV)
    args = parser.parse_args()

    try:
        jobs = read_jobs(args.csv_file)
    except (OSError, ValueError) as error:
        parser.error(str(error))

    pipeline = build_pipeline(PROFILE_PATH, get_embedder())
    rows = [evaluate_job(job, label, pipeline.matcher, pipeline.analyzer) for job, label in jobs]
    print_report(rows, summarize(rows))


if __name__ == "__main__":
    main()
