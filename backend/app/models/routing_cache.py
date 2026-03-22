from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class RoutingCacheEntry(Base, TimestampMixin):
    __tablename__ = "routing_cache_entry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    origin_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    destination_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    plan_day_type: Mapped[str] = mapped_column(String(16), nullable=False)
    departure_bucket: Mapped[str] = mapped_column(String(32), nullable=False)
    routing_preference: Mapped[str] = mapped_column(String(64), nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    distance_meters: Mapped[int | None] = mapped_column(Integer, nullable=True)


class RoutingRequestLog(Base, TimestampMixin):
    __tablename__ = "routing_request_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    element_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
