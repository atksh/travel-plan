from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.trip import Trip


class TripRule(Base, TimestampMixin):
    __tablename__ = "trip_rule"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trip_id: Mapped[int] = mapped_column(
        ForeignKey("trip.id", ondelete="CASCADE"), nullable=False
    )
    rule_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    weight: Mapped[float | None] = mapped_column(nullable=True)
    target_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    target_payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    operator: Mapped[str] = mapped_column(String(32), nullable=False)
    parameters_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    carry_forward_strategy: Mapped[str] = mapped_column(String(32), nullable=False)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_surface: Mapped[str] = mapped_column(String(32), nullable=False)

    trip: Mapped["Trip"] = relationship(back_populates="rules")
