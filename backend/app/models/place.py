from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.trip import TripCandidate


class Place(Base, TimestampMixin):
    __tablename__ = "place"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(64), default="manual", nullable=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tags_json: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    traits_json: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    visit_profile: Mapped["PlaceVisitProfile | None"] = relationship(
        back_populates="place", uselist=False, cascade="all, delete-orphan"
    )
    availability_rules: Mapped[list["PlaceAvailabilityRule"]] = relationship(
        back_populates="place", cascade="all, delete-orphan"
    )
    source_records: Mapped[list["PlaceSourceRecord"]] = relationship(
        back_populates="place", cascade="all, delete-orphan"
    )
    trip_candidates: Mapped[list["TripCandidate"]] = relationship(
        back_populates="place", cascade="all, delete-orphan"
    )


class PlaceVisitProfile(Base, TimestampMixin):
    __tablename__ = "place_visit_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    place_id: Mapped[int] = mapped_column(
        ForeignKey("place.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    stay_min_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    stay_preferred_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    stay_max_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    price_band: Mapped[str | None] = mapped_column(String(32), nullable=True)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    accessibility_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    place: Mapped[Place] = relationship(back_populates="visit_profile")


class PlaceAvailabilityRule(Base, TimestampMixin):
    __tablename__ = "place_availability_rule"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    place_id: Mapped[int] = mapped_column(
        ForeignKey("place.id", ondelete="CASCADE"), nullable=False
    )
    weekday: Mapped[int | None] = mapped_column(Integer, nullable=True)
    open_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    close_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_from: Mapped[str | None] = mapped_column(String(10), nullable=True)
    valid_to: Mapped[str | None] = mapped_column(String(10), nullable=True)
    last_admission_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    closed_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    place: Mapped[Place] = relationship(back_populates="availability_rules")


class PlaceSourceRecord(Base, TimestampMixin):
    __tablename__ = "place_source_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    place_id: Mapped[int] = mapped_column(
        ForeignKey("place.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_place_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    parser_version: Mapped[str] = mapped_column(String(64), default="v1", nullable=False)

    place: Mapped[Place] = relationship(back_populates="source_records")
