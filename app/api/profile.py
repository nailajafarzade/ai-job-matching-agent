"""Profile summary and reload endpoints."""
import yaml
from fastapi import APIRouter, HTTPException, Request

from app.schemas.responses import ProfileSummary, ReloadResult
from app.services.runtime import build_pipeline

router = APIRouter(prefix="/profile", tags=["profile"])


def _profile_summary(profile) -> ProfileSummary:
    return ProfileSummary(
        version=profile.version,
        skills=profile.skills,
        target_roles=[role.title for role in profile.target_roles],
        max_years_required=profile.max_years_required,
        reject_seniority=profile.reject_seniority,
        excluded_job_countries=profile.excluded_job_countries,
    )


@router.get("", response_model=ProfileSummary, summary="Show the active profile summary")
def get_profile(request: Request) -> ProfileSummary:
    return _profile_summary(request.app.state.pipeline.matcher.profile)


@router.post("/reload", response_model=ReloadResult, summary="Reload the profile from its YAML file")
def reload_profile(request: Request) -> ReloadResult:
    current = request.app.state.pipeline
    old_version = current.matcher.profile.version
    try:
        new_pipeline = build_pipeline(
            request.app.state.profile_path,
            request.app.state.embedder,
            request.app.state.min_score,
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError, yaml.YAMLError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    request.app.state.pipeline = new_pipeline
    return ReloadResult(old_version=old_version, new_version=new_pipeline.matcher.profile.version)
