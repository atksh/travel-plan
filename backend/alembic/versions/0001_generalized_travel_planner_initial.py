"""generalized_travel_planner_initial

Revision ID: 0001_generalized_travel_planner_initial
Revises:
Create Date: 2026-03-22 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_generalized_travel_planner_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "place",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lng", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("tags_json", sa.JSON(), nullable=False),
        sa.Column("traits_json", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "place_visit_profile",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("place_id", sa.Integer(), nullable=False),
        sa.Column("stay_min_minutes", sa.Integer(), nullable=False),
        sa.Column("stay_preferred_minutes", sa.Integer(), nullable=False),
        sa.Column("stay_max_minutes", sa.Integer(), nullable=False),
        sa.Column("price_band", sa.String(length=32), nullable=True),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("accessibility_notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["place_id"], ["place.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("place_id"),
    )
    op.create_table(
        "place_availability_rule",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("place_id", sa.Integer(), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=True),
        sa.Column("open_minute", sa.Integer(), nullable=False),
        sa.Column("close_minute", sa.Integer(), nullable=False),
        sa.Column("valid_from", sa.String(length=10), nullable=True),
        sa.Column("valid_to", sa.String(length=10), nullable=True),
        sa.Column("last_admission_minute", sa.Integer(), nullable=True),
        sa.Column("closed_flag", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["place_id"], ["place.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "place_source_record",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("place_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("provider_place_id", sa.String(length=256), nullable=True),
        sa.Column("source_url", sa.String(length=512), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_payload", sa.Text(), nullable=True),
        sa.Column("parser_version", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["place_id"], ["place.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "trip",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("plan_date", sa.Date(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("origin_label", sa.String(length=256), nullable=False),
        sa.Column("origin_lat", sa.Float(), nullable=False),
        sa.Column("origin_lng", sa.Float(), nullable=False),
        sa.Column("destination_label", sa.String(length=256), nullable=False),
        sa.Column("destination_lat", sa.Float(), nullable=False),
        sa.Column("destination_lng", sa.Float(), nullable=False),
        sa.Column("departure_window_start_min", sa.Integer(), nullable=False),
        sa.Column("departure_window_end_min", sa.Integer(), nullable=False),
        sa.Column("end_constraint_kind", sa.String(length=32), nullable=False),
        sa.Column("end_constraint_minute_of_day", sa.Integer(), nullable=False),
        sa.Column("context_weather", sa.String(length=32), nullable=True),
        sa.Column("context_traffic_profile", sa.String(length=32), nullable=True),
        sa.Column("workspace_version", sa.Integer(), nullable=False),
        sa.Column("accepted_run_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "trip_candidate",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trip_id", sa.Integer(), nullable=False),
        sa.Column("place_id", sa.Integer(), nullable=False),
        sa.Column("candidate_state", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=False),
        sa.Column("locked_in", sa.Boolean(), nullable=False),
        sa.Column("locked_out", sa.Boolean(), nullable=False),
        sa.Column("user_note", sa.Text(), nullable=True),
        sa.Column("utility_override", sa.Integer(), nullable=True),
        sa.Column("stay_override_min", sa.Integer(), nullable=True),
        sa.Column("stay_override_preferred", sa.Integer(), nullable=True),
        sa.Column("stay_override_max", sa.Integer(), nullable=True),
        sa.Column("arrive_after_min", sa.Integer(), nullable=True),
        sa.Column("arrive_before_min", sa.Integer(), nullable=True),
        sa.Column("depart_after_min", sa.Integer(), nullable=True),
        sa.Column("depart_before_min", sa.Integer(), nullable=True),
        sa.Column("manual_order_hint", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["trip_id"], ["trip.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["place_id"], ["place.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trip_id", "place_id", name="uq_trip_candidate_trip_id_place_id"),
    )
    op.create_table(
        "trip_rule",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trip_id", sa.Integer(), nullable=False),
        sa.Column("rule_kind", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.Column("target_kind", sa.String(length=32), nullable=False),
        sa.Column("target_payload_json", sa.JSON(), nullable=False),
        sa.Column("operator", sa.String(length=32), nullable=False),
        sa.Column("parameters_json", sa.JSON(), nullable=False),
        sa.Column("carry_forward_strategy", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by_surface", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["trip_id"], ["trip.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "solve_preview",
        sa.Column("preview_id", sa.String(length=64), nullable=False),
        sa.Column("trip_id", sa.Integer(), nullable=False),
        sa.Column("workspace_version", sa.Integer(), nullable=False),
        sa.Column("based_on_run_id", sa.Integer(), nullable=True),
        sa.Column("preview_kind", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("solve_json", sa.JSON(), nullable=False),
        sa.Column("draft_context_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["trip_id"], ["trip.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("preview_id"),
    )
    op.create_table(
        "solve_run",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trip_id", sa.Integer(), nullable=False),
        sa.Column("run_kind", sa.String(length=32), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("workspace_version", sa.Integer(), nullable=False),
        sa.Column("based_on_preview_id", sa.String(length=64), nullable=True),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("warnings_json", sa.JSON(), nullable=False),
        sa.Column("rule_results_json", sa.JSON(), nullable=False),
        sa.Column("candidate_diagnostics_json", sa.JSON(), nullable=False),
        sa.Column("alternatives_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["trip_id"], ["trip.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "solve_stop",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("solve_run_id", sa.Integer(), nullable=False),
        sa.Column("sequence_order", sa.Integer(), nullable=False),
        sa.Column("node_kind", sa.String(length=16), nullable=False),
        sa.Column("place_id", sa.Integer(), nullable=True),
        sa.Column("label", sa.String(length=256), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lng", sa.Float(), nullable=False),
        sa.Column("arrival_min", sa.Integer(), nullable=False),
        sa.Column("departure_min", sa.Integer(), nullable=False),
        sa.Column("stay_min", sa.Integer(), nullable=False),
        sa.Column("leg_from_prev_min", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["solve_run_id"], ["solve_run.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "solve_route_leg",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("solve_run_id", sa.Integer(), nullable=False),
        sa.Column("from_sequence_order", sa.Integer(), nullable=False),
        sa.Column("to_sequence_order", sa.Integer(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("distance_meters", sa.Integer(), nullable=True),
        sa.Column("encoded_polyline", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["solve_run_id"], ["solve_run.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "execution_session",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trip_id", sa.Integer(), nullable=False),
        sa.Column("active_run_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_stop_sequence_order", sa.Integer(), nullable=True),
        sa.Column("suffix_origin_kind", sa.String(length=32), nullable=True),
        sa.Column("suffix_origin_payload_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["trip_id"], ["trip.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trip_id", name="uq_execution_session_trip_id"),
    )
    op.create_table(
        "execution_event",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trip_id", sa.Integer(), nullable=False),
        sa.Column("execution_session_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["trip_id"], ["trip.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["execution_session_id"], ["execution_session.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "routing_cache_entry",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("origin_hash", sa.String(length=64), nullable=False),
        sa.Column("destination_hash", sa.String(length=64), nullable=False),
        sa.Column("plan_day_type", sa.String(length=16), nullable=False),
        sa.Column("departure_bucket", sa.String(length=32), nullable=False),
        sa.Column("routing_preference", sa.String(length=64), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("distance_meters", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_routing_cache_entry_origin_hash"),
        "routing_cache_entry",
        ["origin_hash"],
        unique=False,
    )
    op.create_index(
        op.f("ix_routing_cache_entry_destination_hash"),
        "routing_cache_entry",
        ["destination_hash"],
        unique=False,
    )
    op.create_table(
        "routing_request_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("request_kind", sa.String(length=32), nullable=False),
        sa.Column("element_count", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=False),
        sa.Column("cache_hit", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("routing_request_log")
    op.drop_index(op.f("ix_routing_cache_entry_destination_hash"), table_name="routing_cache_entry")
    op.drop_index(op.f("ix_routing_cache_entry_origin_hash"), table_name="routing_cache_entry")
    op.drop_table("routing_cache_entry")
    op.drop_table("execution_event")
    op.drop_table("execution_session")
    op.drop_table("solve_route_leg")
    op.drop_table("solve_stop")
    op.drop_table("solve_run")
    op.drop_table("solve_preview")
    op.drop_table("trip_rule")
    op.drop_table("trip_candidate")
    op.drop_table("trip")
    op.drop_table("place_source_record")
    op.drop_table("place_availability_rule")
    op.drop_table("place_visit_profile")
    op.drop_table("place")
