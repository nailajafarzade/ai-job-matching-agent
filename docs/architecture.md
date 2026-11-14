# Architecture

## Modules

| Module | Responsibility |
|--------|----------------|
| `app/api/` | JSON endpoints for jobs, collectors, applications, and statistics |
| `app/analysis/` | Rule-based extraction of required skills, years, and seniority |
| `app/collectors/` | Public API clients, conservative text parsing, and polite run limits |
| `app/documents/` | CV registry, CV choice, profile-backed facts, letters, and reviewer |
| `app/matching/` | Eligibility filters and explainable skill, semantic, and title scores |
| `app/profile/` | Validates and loads the owner's profile and confirmed project facts |
| `app/senders/` | Local manual packages and explicitly confirmed email delivery |
| `app/services/` | Job pipeline, preparation, approval, tracking, statistics, and sending workflows |
| `app/web/` | Server-rendered dashboard and human form actions |
| `migrations/` | Alembic baseline and database upgrades |

The normal flow is collect or submit a job, analyze it, apply hard filters, score
it, prepare a profile-backed application, and let a person review and approve
it. Matching uses the configured local embedding model, while tests and the
offline demo use `HashingEmbedder` and do not download a model.

## Database tables

| Table | Contents |
|-------|----------|
| `jobs` | Original post fields, source, application contact, eligibility, and deduplication hash |
| `job_analyses` | Parsed requirements and seniority, versioned by analyzer |
| `matches` | Decision, score parts, explanations, versions, and skill lists |
| `collector_runs` | Per-source collection times, counts, and errors |
| `applications` | One CV choice, letter, reviewer result, status, and timestamps per job |
| `application_events` | Append-only status transitions and human notes |

## Application status machine

| Current | Allowed next statuses |
|---------|-----------------------|
| `prepared` | `approved`, `skipped` |
| `approved` | `package_ready`, `sent`, `skipped`, `prepared` |
| `package_ready` | `sent`, `skipped` |
| `sent` | `replied`, `interview`, `rejected`, `withdrawn` |
| `replied` | `interview`, `rejected`, `withdrawn` |
| `interview` | `rejected`, `withdrawn` |
| `skipped` | `prepared` |
| `rejected`, `withdrawn` | none |

All status changes go through `app/services/tracker.py` and produce an
`application_events` row. Real email is only available after approval and an
additional confirmation; dry-run email and manual package preparation do not
send an email.