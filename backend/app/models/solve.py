from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.trip import Trip


class SolvePreview(Base, TimestampMixin):
    __tablename__ = "solve_preview"

    preview_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    trip_id: Mapped[int] = mapped_column(
        ForeignKey("trip.id", ondelete="CASCADE"), nullable=False
    )
    workspace_version: Mapped[int] = mapped_column(Integer, nullable=False)
    based_on_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    preview_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    solve_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    draft_context_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    trip: Mapped["Trip"] = relationship(back_populates="solve_previews")


class SolveRun(Base, TimestampMixin):
    __tablename__ = "solve_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trip_id: Mapped[int] = mapped_column(
        ForeignKey("trip.id", ondelete="CASCADE"), nullable=False
    )
    run_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    workspace_version: Mapped[int] = mapped_column(Integer, nullable=False)
    based_on_preview_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    warnings_json: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    rule_results_json: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    candidate_diagnostics_json: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    alternatives_json: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)

    trip: Mapped["Trip"] = relationship(back_populates="solve_runs")
    stops: Mapped[list["SolveStop"]] = relationship(
        back_populates="solve_run", cascade="all, delete-orphan"
    )
    route_legs: Mapped[list["SolveRouteLeg"]] = relationship(
        back_populates="solve_run", cascade="all, delete-orphan"
    )


class SolveStop(Base, TimestampMixin):
    __tablename__ = "solve_stop"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    solve_run_id: Mapped[int] = mapped_column(
        ForeignKey("solve_run.id", ondelete="CASCADE"), nullable=False
    )
    sequence_order: Mapped[int] = mapped_column(Integer, nullable=False)
    node_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    place_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    arrival_min: Mapped[int] = mapped_column(Integer, nullable=False)
    departure_min: Mapped[int] = mapped_column(Integer, nullable=False)
    stay_min: Mapped[int] = mapped_column(Integer, nullable=False)
    leg_from_prev_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)

    solve_run: Mapped["SolveRun"] = relationship(back_populates="stops")


class SolveRouteLeg(Base, TimestampMixin):
    __tablename__ = "solve_route_leg"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    solve_run_id: Mapped[int] = mapped_column(
        ForeignKey("solve_run.id", ondelete="CASCADE"), nullable=False
    )
    from_sequence_order: Mapped[int] = mapped_column(Integer, nullable=False)
    to_sequence_order: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    distance_meters: Mapped[int | None] = mapped_column(Integer, nullable=True)
    encoded_polyline: Mapped[str] = mapped_column(String, nullable=False)

    solve_run: Mapped["SolveRun"] = relationship(back_populates="route_legs")
