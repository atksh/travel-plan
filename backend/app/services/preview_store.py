from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.errors import RequestContractError
from app.models.solve import SolvePreview
from app.models.trip import Trip


PREVIEW_TTL_MINUTES = 30


def create_preview(
    session: Session,
    *,
    trip: Trip,
    preview_kind: str,
    solve_payload: dict,
    draft_context: dict,
) -> SolvePreview:
    preview = SolvePreview(
        preview_id=f"pvw_{uuid4().hex[:16]}",
        trip_id=trip.id,
        workspace_version=trip.workspace_version,
        based_on_run_id=trip.accepted_run_id,
        preview_kind=preview_kind,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=PREVIEW_TTL_MINUTES),
        solve_json=solve_payload,
        draft_context_json=draft_context,
    )
    session.add(preview)
    session.flush()
    return preview


def get_preview_or_error(session: Session, preview_id: str) -> SolvePreview:
    preview = session.get(SolvePreview, preview_id)
    if preview is None:
        raise RequestContractError(
            "PREVIEW_NOT_FOUND",
            "The requested preview does not exist.",
            status_code=404,
        )
    expires_at = preview.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        raise RequestContractError(
            "PREVIEW_EXPIRED",
            "The requested preview has expired.",
            status_code=409,
        )
    return preview


def assert_preview_matches_workspace(*, trip: Trip, preview: SolvePreview, workspace_version: int) -> None:
    if preview.trip_id != trip.id or workspace_version != trip.workspace_version or preview.workspace_version != trip.workspace_version:
        raise RequestContractError(
            "WORKSPACE_VERSION_MISMATCH",
            "The preview was generated from a different workspace version.",
            details={
                "trip_workspace_version": trip.workspace_version,
                "preview_workspace_version": preview.workspace_version,
                "request_workspace_version": workspace_version,
            },
            status_code=409,
        )
