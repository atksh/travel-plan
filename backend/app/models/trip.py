from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.poi import PoiMaster


class TripPlan(Base, TimestampMixin):
    __tablename__ = "trip_plan"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    state: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    plan_date: Mapped[date] = mapped_column(Date, nullable=False)
    origin_lat: Mapped[float] = mapped_column(Float, nullable=False)
    origin_lng: Mapped[float] = mapped_column(Float, nullable=False)
    origin_label: Mapped[str] = mapped_column(String(256), default="Start", nullable=False)
    dest_lat: Mapped[float] = mapped_column(Float, nullable=False)
    dest_lng: Mapped[float] = mapped_column(Float, nullable=False)
    dest_label: Mapped[str] = mapped_column(String(256), default="End", nullable=False)
    departure_window_start_min: Mapped[int] = mapped_column(Integer, nullable=False)
    departure_window_end_min: Mapped[int] = mapped_column(Integer, nullable=False)
    return_deadline_min: Mapped[int] = mapped_column(Integer, nullable=False)
    weather_mode: Mapped[str] = mapped_column(String(16), default="normal", nullable=False)

    preference_profile: Mapped["TripPreferenceProfile | None"] = relationship(
        back_populates="trip", uselist=False, cascade="all, delete-orphan"
    )
    candidates: Mapped[list["TripCandidate"]] = relationship(
        back_populates="trip", cascade="all, delete-orphan"
    )
    execution_events: Mapped[list["TripExecutionEvent"]] = relationship(
        back_populates="trip", cascade="all, delete-orphan"
    )
    solver_runs: Mapped[list["SolverRun"]] = relationship(
        back_populates="trip", cascade="all, delete-orphan"
    )


class TripPreferenceProfile(Base, TimestampMixin):
    __tablename__ = "trip_preference_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trip_id: Mapped[int] = mapped_column(
        ForeignKey("trip_plan.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    driving_penalty_weight: Mapped[float] = mapped_column(Float, default=0.05, nullable=False)
    max_continuous_drive_minutes: Mapped[int] = mapped_column(Integer, default=120, nullable=False)
    preferred_lunch_tags: Mapped[list[Any]] = mapped_column(JSON, default=list)
    preferred_dinner_tags: Mapped[list[Any]] = mapped_column(JSON, default=list)
    must_have_cafe: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    budget_band: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pace_style: Mapped[str] = mapped_column(String(32), default="balanced", nullable=False)

    trip: Mapped[TripPlan] = relationship(back_populates="preference_profile")


class TripCandidate(Base, TimestampMixin):
    __tablename__ = "trip_candidate"
    __table_args__ = (
        UniqueConstraint("trip_id", "poi_id", name="uq_trip_candidate_trip_id_poi_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trip_id: Mapped[int] = mapped_column(
        ForeignKey("trip_plan.id", ondelete="CASCADE"), nullable=False
    )
    poi_id: Mapped[int] = mapped_column(ForeignKey("poi_master.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="seed", nullable=False)
    must_visit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    excluded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    locked_in: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    locked_out: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    user_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    utility_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    candidate_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)

    trip: Mapped[TripPlan] = relationship(back_populates="candidates")
    poi: Mapped["PoiMaster"] = relationship()


class TripExecutionEvent(Base, TimestampMixin):
    __tablename__ = "trip_execution_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trip_id: Mapped[int] = mapped_column(
        ForeignKey("trip_plan.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    trip: Mapped[TripPlan] = relationship(back_populates="execution_events")


class SolverRun(Base, TimestampMixin):
    __tablename__ = "solver_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trip_id: Mapped[int] = mapped_column(
        ForeignKey("trip_plan.id", ondelete="CASCADE"), nullable=False
    )
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    solve_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    solve_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    objective_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    infeasible_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    route_summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    trip: Mapped[TripPlan] = relationship(back_populates="solver_runs")
    planned_stops: Mapped[list["PlannedStop"]] = relationship(
        back_populates="solver_run", cascade="all, delete-orphan"
    )


class PlannedStop(Base, TimestampMixin):
    __tablename__ = "planned_stop"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    solver_run_id: Mapped[int] = mapped_column(
        ForeignKey("solver_run.id", ondelete="CASCADE"), nullable=False
    )
    sequence_order: Mapped[int] = mapped_column(Integer, nullable=False)
    poi_id: Mapped[int | None] = mapped_column(ForeignKey("poi_master.id"), nullable=True)
    label: Mapped[str | None] = mapped_column(String(256), nullable=True)
    node_kind: Mapped[str] = mapped_column(String(16), nullable=False)  # start, poi, end
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    arrival_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    departure_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stay_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    leg_from_prev_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="planned", nullable=False)

    solver_run: Mapped[SolverRun] = relationship(back_populates="planned_stops")
    poi: Mapped["PoiMaster | None"] = relationship()
