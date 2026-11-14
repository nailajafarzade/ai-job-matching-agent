"""Baseline schema for jobs and match results."""
from alembic import op
import sqlalchemy as sa

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("company", sa.String(length=300), nullable=False),
        sa.Column("location", sa.String(length=300), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("remote_type", sa.String(length=20), nullable=False),
        sa.Column("eligible_countries", sa.JSON(), nullable=False),
        sa.Column("remote_work_eligibility", sa.String(length=20), nullable=False),
        sa.Column("location_restrictions", sa.Text(), nullable=True),
        sa.Column("description_raw", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_jobs_content_hash", "jobs", ["content_hash"], unique=True)

    op.create_table(
        "job_analyses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("analyzer_version", sa.String(length=20), nullable=False),
        sa.Column("required_skills", sa.JSON(), nullable=False),
        sa.Column("nice_to_have_skills", sa.JSON(), nullable=False),
        sa.Column("min_years", sa.Integer(), nullable=True),
        sa.Column("seniority", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "analyzer_version", name="uq_analysis_job_version"),
    )
    op.create_index("ix_job_analyses_job_id", "job_analyses", ["job_id"], unique=False)

    op.create_table(
        "matches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("analysis_id", sa.Integer(), nullable=True),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("reject_reasons", sa.JSON(), nullable=False),
        sa.Column("review_reasons", sa.JSON(), nullable=False),
        sa.Column("final_score", sa.Float(), nullable=True),
        sa.Column("skill_score", sa.Float(), nullable=True),
        sa.Column("semantic_score", sa.Float(), nullable=True),
        sa.Column("title_score", sa.Float(), nullable=True),
        sa.Column("matched_skills", sa.JSON(), nullable=False),
        sa.Column("studied_skills", sa.JSON(), nullable=False),
        sa.Column("missing_skills", sa.JSON(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("matcher_version", sa.String(length=20), nullable=False),
        sa.Column("embedding_model", sa.String(length=100), nullable=True),
        sa.Column("weights", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["analysis_id"], ["job_analyses.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_matches_job_id", "matches", ["job_id"], unique=False)
    op.create_index("ix_matches_job_created", "matches", ["job_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_matches_job_created", table_name="matches")
    op.drop_index("ix_matches_job_id", table_name="matches")
    op.drop_table("matches")
    op.drop_index("ix_job_analyses_job_id", table_name="job_analyses")
    op.drop_table("job_analyses")
    op.drop_index("ix_jobs_content_hash", table_name="jobs")
    op.drop_table("jobs")
