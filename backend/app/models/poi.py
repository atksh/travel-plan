from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.source import PoiSourceSnapshot


class PoiMaster(Base, TimestampMixin):
    __tablename__ = "poi_master"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    seed_key: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    google_place_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    primary_category: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    planning_profile: Mapped["PoiPlanningProfile | None"] = relationship(
        back_populates="poi", uselist=False
    )
    opening_rules: Mapped[list["PoiOpeningRule"]] = relationship(
        back_populates="poi", cascade="all, delete-orphan"
    )
    source_snapshots: Mapped[list["PoiSourceSnapshot"]] = relationship(
        back_populates="poi", cascade="all, delete-orphan"
    )
    tag_links: Mapped[list["PoiTagLink"]] = relationship(
        back_populates="poi", cascade="all, delete-orphan"
    )
    dependency_rules_from: Mapped[list["PoiDependencyRule"]] = relationship(
        foreign_keys="PoiDependencyRule.if_visit_poi_id",
        back_populates="if_visit_poi",
        cascade="all, delete-orphan",
    )


class PoiPlanningProfile(Base, TimestampMixin):
    __tablename__ = "poi_planning_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    poi_id: Mapped[int] = mapped_column(
        ForeignKey("poi_master.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    stay_min_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    stay_max_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    meal_window_start_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meal_window_end_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_indoor: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sunset_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    scenic_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    relax_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    price_band: Mapped[str | None] = mapped_column(String(16), nullable=True)
    parking_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    difficulty_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    utility_default: Mapped[int] = mapped_column(Integer, default=10, nullable=False)

    poi: Mapped[PoiMaster] = relationship(back_populates="planning_profile")


class PoiOpeningRule(Base, TimestampMixin):
    __tablename__ = "poi_opening_rule"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    poi_id: Mapped[int] = mapped_column(
        ForeignKey("poi_master.id", ondelete="CASCADE"), nullable=False
    )
    weekday: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # 0=Mon .. 6=Sun, None=all days
    open_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    close_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_from: Mapped[str | None] = mapped_column(String(10), nullable=True)  # YYYY-MM-DD
    valid_to: Mapped[str | None] = mapped_column(String(10), nullable=True)
    holiday_note: Mapped[str | None] = mapped_column(String(256), nullable=True)
    last_admission_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)

    poi: Mapped[PoiMaster] = relationship(back_populates="opening_rules")


class PoiTag(Base, TimestampMixin):
    __tablename__ = "poi_tag"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(128), nullable=False)

    links: Mapped[list["PoiTagLink"]] = relationship(back_populates="tag")


class PoiTagLink(Base, TimestampMixin):
    __tablename__ = "poi_tag_link"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    poi_id: Mapped[int] = mapped_column(
        ForeignKey("poi_master.id", ondelete="CASCADE"), nullable=False
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("poi_tag.id", ondelete="CASCADE"), nullable=False
    )

    poi: Mapped[PoiMaster] = relationship(back_populates="tag_links")
    tag: Mapped[PoiTag] = relationship(back_populates="links")

    __table_args__ = (UniqueConstraint("poi_id", "tag_id", name="uq_poi_tag"),)


class PoiDependencyRule(Base, TimestampMixin):
    __tablename__ = "poi_dependency_rule"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    if_visit_poi_id: Mapped[int] = mapped_column(
        ForeignKey("poi_master.id", ondelete="CASCADE"), nullable=False
    )
    require_poi_id: Mapped[int] = mapped_column(
        ForeignKey("poi_master.id", ondelete="CASCADE"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    if_visit_poi: Mapped[PoiMaster] = relationship(
        foreign_keys=[if_visit_poi_id], back_populates="dependency_rules_from"
    )
