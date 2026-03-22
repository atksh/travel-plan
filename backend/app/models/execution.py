from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.trip import Trip


class ExecutionSession(Base, TimestampMixin):
    __tablename__ = "execution_session"
    __table_args__ = (UniqueConstraint("trip_id", name="uq_execution_session_trip_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trip_id: Mapped[int] = mapped_column(
        ForeignKey("trip.id", ondelete="CASCADE"), nullable=False
    )
    active_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_stop_sequence_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    suffix_origin_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    suffix_origin_payload_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )

    trip: Mapped["Trip"] = relationship(back_populates="execution_session")
    events: Mapped[list["ExecutionEvent"]] = relationship(
        back_populates="execution_session", cascade="all, delete-orphan"
    )


class ExecutionEvent(Base, TimestampMixin):
    __tablename__ = "execution_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trip_id: Mapped[int] = mapped_column(
        ForeignKey("trip.id", ondelete="CASCADE"), nullable=False
    )
    execution_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("execution_session.id", ondelete="CASCADE"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    execution_session: Mapped["ExecutionSession | None"] = relationship(back_populates="events")
