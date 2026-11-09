"""Try the analyzer and matcher on one job text, in the terminal.

Run from the project root (the first run downloads the embedding model):

    python -m scripts.try_match job.txt --title "Junior Java Developer" --remote --eligible Azerbaijan

Use it with real job posts to see where the rules are wrong. Then fix the
rules or the numbers in app/config.py.
"""
import argparse
from pathlib import Path

from app.analysis.analyzer import get_analyzer
from app.analysis.vocabulary import get_vocabulary
from app.matching.embeddings import get_embedder
from app.matching.scorer import Matcher
from app.matching.types import JobFacts
from app.profile.loader import load_profile
from app.schemas.enums import RemoteEligibility, RemoteType


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", type=Path, help="text file with the job post")
    parser.add_argument("--title", required=True)
    parser.add_argument("--country")
    parser.add_argument("--location")
    parser.add_argument("--remote", action="store_true", help="the job is remote")
    parser.add_argument("--onsite", action="store_true", help="the job is on-site")
    parser.add_argument("--eligible", nargs="*", default=[], help="countries that can apply (remote jobs)")
    parser.add_argument("--restrictions", help="location restrictions text")
    args = parser.parse_args()

    remote_type = RemoteType.remote if args.remote else RemoteType.onsite if args.onsite else RemoteType.unknown
    job = JobFacts(
        title=args.title,
        description=args.file.read_text(encoding="utf-8"),
        country=args.country,
        location=args.location,
        remote_type=remote_type,
        eligible_countries=args.eligible,
        remote_work_eligibility=RemoteEligibility.unknown,
        location_restrictions=args.restrictions,
    )

    analysis = get_analyzer().analyze(job.title, job.description)
    print("ANALYSIS")
    print("  required :", ", ".join(analysis.required_skills) or "-")
    print("  nice     :", ", ".join(analysis.nice_to_have_skills) or "-")
    print("  min years:", analysis.min_years)
    print("  seniority:", analysis.seniority.value)

    matcher = Matcher(load_profile(), get_vocabulary(), get_embedder())
    result = matcher.match(job, analysis)
    print("\nMATCH")
    print("  decision :", result.decision.value)
    if result.final_score is not None:
        print(f"  final    : {result.final_score}")
        print(f"  skill    : {result.skill_score}")
        print(f"  semantic : {result.semantic_score}")
        print(f"  title    : {result.title_score}")
    print("\n" + result.explanation)


if __name__ == "__main__":
    main()
