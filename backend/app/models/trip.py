from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.execution import ExecutionSession
    from app.models.place import Place
    from app.models.rule import TripRule
    from app.models.solve import SolvePreview, SolveRun


class Trip(Base, TimestampMixin):
    __tablename__ = "trip"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    plan_date: Mapped[date] = mapped_column(Date, nullable=False)
    state: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    origin_label: Mapped[str] = mapped_column(String(256), nullable=False)
    origin_lat: Mapped[float] = mapped_column(Float, nullable=False)
    origin_lng: Mapped[float] = mapped_column(Float, nullable=False)
    destination_label: Mapped[str] = mapped_column(String(256), nullable=False)
    destination_lat: Mapped[float] = mapped_column(Float, nullable=False)
    destination_lng: Mapped[float] = mapped_column(Float, nullable=False)
    departure_window_start_min: Mapped[int] = mapped_column(Integer, nullable=False)
    departure_window_end_min: Mapped[int] = mapped_column(Integer, nullable=False)
    end_constraint_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    end_constraint_minute_of_day: Mapped[int] = mapped_column(Integer, nullable=False)
    context_weather: Mapped[str | None] = mapped_column(String(32), nullable=True)
    context_traffic_profile: Mapped[str | None] = mapped_column(String(32), nullable=True)
    workspace_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    accepted_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    candidates: Mapped[list["TripCandidate"]] = relationship(
        back_populates="trip", cascade="all, delete-orphan"
    )
    rules: Mapped[list["TripRule"]] = relationship(
        back_populates="trip", cascade="all, delete-orphan"
    )
    solve_previews: Mapped[list["SolvePreview"]] = relationship(
        back_populates="trip", cascade="all, delete-orphan"
    )
    solve_runs: Mapped[list["SolveRun"]] = relationship(
        back_populates="trip", cascade="all, delete-orphan"
    )
    execution_session: Mapped["ExecutionSession | None"] = relationship(
        back_populates="trip", uselist=False, cascade="all, delete-orphan"
    )


class TripCandidate(Base, TimestampMixin):
    __tablename__ = "trip_candidate"
    __table_args__ = (
        UniqueConstraint("trip_id", "place_id", name="uq_trip_candidate_trip_id_place_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trip_id: Mapped[int] = mapped_column(
        ForeignKey("trip.id", ondelete="CASCADE"), nullable=False
    )
    place_id: Mapped[int] = mapped_column(
        ForeignKey("place.id", ondelete="CASCADE"), nullable=False
    )
    candidate_state: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    priority: Mapped[str] = mapped_column(String(16), default="normal", nullable=False)
    locked_in: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    locked_out: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    user_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    utility_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stay_override_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stay_override_preferred: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stay_override_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    arrive_after_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    arrive_before_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    depart_after_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    depart_before_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    manual_order_hint: Mapped[int | None] = mapped_column(Integer, nullable=True)

    trip: Mapped[Trip] = relationship(back_populates="candidates")
    place: Mapped["Place"] = relationship(back_populates="trip_candidates")
