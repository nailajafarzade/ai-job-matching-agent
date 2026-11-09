# Job Agent

An AI agent that helps with job search: it reads job posts, scores how well
they fit my profile, and (in later stages) prepares CVs and letters.

The decision logic is written by hand. It is simple and every score can be
explained.

## Principles

- The agent never invents skills or experience. It only uses `data/profile.yaml`.
- Skill level and project tech stack are kept separate. Using a skill does not
  prove that a project used it.
- `data/skills.yaml` is only a vocabulary to recognize skills in job posts.
  A skill listed there is not mine unless it is also in `profile.yaml`.
- Missing skills are shown as `missing_skills`. They are never added to the profile.
- Synonyms are true synonyms only. Related technologies are separate skills.
- Plain code does collecting, filtering and statuses. Models help only with
  analysis and text.
- Every match result shows each part of the score and the reason.
- Profile version and matcher version are saved with each result.
- The embedding model is loaded once at app start.
- A human approves every application.

## Stages

| # | Stage | Status |
|---|-------|--------|
| 1 | Manual intake + job analysis + matching | in progress (profile, models, analyzer and matcher done; pipeline and API next) |
| 2 | CV selection + CV tailoring | planned |
| 3 | Ollama + cover letter + reviewer | planned |
| 4 | Dashboard + human approval + tracker | planned |
| 5 | Automatic job collectors (RemoteOK, Remotive) | planned |
| 6 | Application automation (only where allowed) | planned |

## Stage 1 setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload    # then open http://127.0.0.1:8000/docs
```

## Folders

```
app/
  api/        HTTP endpoints
  analysis/   find skills, years, seniority in a job text
  db/         database models and session
  intake/     manual job input and text cleaning
  matching/   filters, embeddings, scorer
  profile/    loads and versions profile.yaml
  schemas/    Pydantic models
  services/   pipeline: intake -> analysis -> matching
data/         profile.yaml, skills.yaml
tests/
```

## Matching

1. Hard filter (separate from the semantic part):
   - seniority: senior, lead, principal, staff, manager
   - more than 2 years of required experience
   - India-based jobs
   - remote jobs must accept applicants from Azerbaijan; unknown means
     "flag for manual review"
2. Skill score: how many required skills I have (weighted).
3. Semantic score: similarity between the job text and my profile texts.
4. Title score: similarity between the job title and my target roles.
5. Final = `0.45 * skill + 0.35 * semantic + 0.20 * title` (see `app/config.py`).

The result shows the final score, the three parts, matched skills,
missing skills and the reason.

## Data model

| Table | What it holds |
|-------|---------------|
| `jobs` | The raw job post, eligibility fields, `content_hash` (unique, for dedupe), status |
| `job_analyses` | Required and nice-to-have skills, min years, seniority, one row per analyzer version |
| `matches` | Decision, reasons, all score parts, matched and missing skills, explanation, profile version, matcher version, embedding model, weights used |

Rejected jobs have no scores, only `reject_reasons`. Unknown remote eligibility
gives `needs_review`, not a silent reject.

Run the tests: `python -m pytest`

## Analyzer (rules only, no model)

`app/analysis/` turns a job text into: required skills, nice-to-have skills,
minimum years, seniority.

- `vocabulary.py`: finds skills from `skills.yaml`. Longest name wins
  ("Spring Boot" is one skill). Whole words only ("Java" is not in "JavaScript").
  Only true synonyms count. `related` skills are never matched.
  Ambiguous words ("REST", "Spring", "React") count only in their skill form,
  so "the rest of the team" is ignored.
- `sections.py`: tags each sentence as required, nice-to-have or ignore
  (headings like "Nice to have:", "About us", and phrases like "is a plus").
  Skills found only in "About us" or "Benefits" are not requirements.
- `experience.py`: minimum years ("1-2 years" gives 1, "no experience required"
  gives 0, not stated gives `None`). Nice-to-have years are ignored.
- `seniority.py`: the title decides. Description phrases like
  "mentor junior developers" are not used.

## Matcher (`app/matching/`)

- `filters.py`: hard filters. Reject: seniority, more than 2 years, India,
  remote job that does not accept Azerbaijan. Needs review (never silently
  rejected): remote eligibility unknown, on-site job abroad, location not stated.
- `skills_score.py`: weighted. Required skills full weight, nice-to-have x0.4.
  Hands-on skill = full credit, studied = half, missing = zero and listed in
  `missing_skills`. Related skills give no credit.
- `embeddings.py`: `Embedder` interface. The real model loads once (`get_embedder`).
- `similarity.py`: semantic score (job text vs my profile texts) and title score
  (job title vs target roles, scaled by role priority).
- `scorer.py`: runs filters first. A rejected job gets no scores and no embedding work.
  If a job names no known skill, the skill weight is dropped and the others are rescaled.
  Decision order: rejected, below_threshold, needs_review, queued.

The numbers that turn cosine similarity into 0-100 (`SEMANTIC_FLOOR/CEIL`,
`TITLE_FLOOR/CEIL` in `config.py`) are a first guess. Tune them with real jobs.

Try it on a real job post:

```bash
python -m scripts.try_match job.txt --title "Junior Java Developer" --remote --eligible Azerbaijan
```

Tests use a small fake embedder, so they are fast. `tests/test_real_embedder.py`
uses the real model and is skipped when the model is not available.

## Job fields for remote eligibility

`eligible_countries`, `remote_work_eligibility`, `location_restrictions`
(added to the job schema when we build it).
