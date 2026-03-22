from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.place import Place
from app.models.rule import TripRule
from app.models.solve import SolveRouteLeg, SolveRun, SolveStop
from app.models.trip import Trip, TripCandidate


def increment_workspace_version(trip: Trip) -> None:
    trip.workspace_version += 1


def serialize_place_summary(place: Place) -> dict:
    return {
        "id": place.id,
        "name": place.name,
        "lat": place.lat,
        "lng": place.lng,
        "source": place.source,
        "archived": place.archived,
        "category": place.category,
        "tags": list(place.tags_json or []),
        "traits": list(place.traits_json or []),
    }


def serialize_place_detail(place: Place) -> dict:
    return {
        **serialize_place_summary(place),
        "visit_profile": None
        if place.visit_profile is None
        else {
            "stay_min_minutes": place.visit_profile.stay_min_minutes,
            "stay_preferred_minutes": place.visit_profile.stay_preferred_minutes,
            "stay_max_minutes": place.visit_profile.stay_max_minutes,
            "price_band": place.visit_profile.price_band,
            "rating": place.visit_profile.rating,
            "accessibility_notes": place.visit_profile.accessibility_notes,
        },
        "availability_rules": [
            {
                "weekday": rule.weekday,
                "open_minute": rule.open_minute,
                "close_minute": rule.close_minute,
                "valid_from": rule.valid_from,
                "valid_to": rule.valid_to,
                "last_admission_minute": rule.last_admission_minute,
                "closed_flag": rule.closed_flag,
            }
            for rule in sorted(
                place.availability_rules,
                key=lambda item: (item.weekday is None, item.weekday or -1, item.open_minute),
            )
        ],
        "source_records": [
            {
                "provider": record.provider,
                "provider_place_id": record.provider_place_id,
                "source_url": record.source_url,
                "fetched_at": record.fetched_at.isoformat(),
                "parser_version": record.parser_version,
            }
            for record in place.source_records
        ],
        "notes": place.notes,
    }


def serialize_trip_detail(trip: Trip) -> dict:
    return {
        "id": trip.id,
        "title": trip.title,
        "plan_date": trip.plan_date,
        "state": trip.state,
        "timezone": trip.timezone,
        "origin": {
            "label": trip.origin_label,
            "lat": trip.origin_lat,
            "lng": trip.origin_lng,
        },
        "destination": {
            "label": trip.destination_label,
            "lat": trip.destination_lat,
            "lng": trip.destination_lng,
        },
        "departure_window_start_min": trip.departure_window_start_min,
        "departure_window_end_min": trip.departure_window_end_min,
        "end_constraint": {
            "kind": trip.end_constraint_kind,
            "minute_of_day": trip.end_constraint_minute_of_day,
        },
        "context": {
            "weather": trip.context_weather,
            "traffic_profile": trip.context_traffic_profile or "default",
        },
    }


def serialize_candidate(candidate: TripCandidate) -> dict:
    return {
        "id": candidate.id,
        "place_id": candidate.place_id,
        "candidate_state": candidate.candidate_state,
        "priority": candidate.priority,
        "locked_in": candidate.locked_in,
        "locked_out": candidate.locked_out,
        "utility_override": candidate.utility_override,
        "stay_override": {
            "min": candidate.stay_override_min,
            "preferred": candidate.stay_override_preferred,
            "max": candidate.stay_override_max,
        },
        "time_preference": {
            "arrive_after_min": candidate.arrive_after_min,
            "arrive_before_min": candidate.arrive_before_min,
            "depart_after_min": candidate.depart_after_min,
            "depart_before_min": candidate.depart_before_min,
        },
        "manual_order_hint": candidate.manual_order_hint,
        "user_note": candidate.user_note,
        "place": serialize_place_summary(candidate.place),
    }


def serialize_rule(rule: TripRule) -> dict:
    return {
        "id": rule.id,
        "trip_id": rule.trip_id,
        "rule_kind": rule.rule_kind,
        "scope": rule.scope,
        "mode": rule.mode,
        "weight": rule.weight,
        "target": {
            "kind": rule.target_kind,
            "value": rule.target_payload_json.get("value"),
            "data": {
                key: value
                for key, value in rule.target_payload_json.items()
                if key != "value"
            },
        },
        "operator": rule.operator,
        "parameters": dict(rule.parameters_json or {}),
        "carry_forward_strategy": rule.carry_forward_strategy,
        "label": rule.label,
        "description": rule.description,
        "created_by_surface": rule.created_by_surface,
    }


def serialize_solve_run(run: SolveRun, *, stops: list[SolveStop], route_legs: list[SolveRouteLeg]) -> dict:
    return {
        "summary": dict(run.summary_json or {}),
        "stops": [
            {
                "sequence_order": stop.sequence_order,
                "node_kind": stop.node_kind,
                "place_id": stop.place_id,
                "label": stop.label,
                "lat": stop.lat,
                "lng": stop.lng,
                "arrival_min": stop.arrival_min,
                "departure_min": stop.departure_min,
                "stay_min": stop.stay_min,
                "leg_from_prev_min": stop.leg_from_prev_min,
                "status": stop.status,
            }
            for stop in sorted(stops, key=lambda item: item.sequence_order)
        ],
        "route_legs": [
            {
                "from_sequence_order": leg.from_sequence_order,
                "to_sequence_order": leg.to_sequence_order,
                "duration_minutes": leg.duration_minutes,
                "distance_meters": leg.distance_meters,
                "encoded_polyline": leg.encoded_polyline,
            }
            for leg in sorted(route_legs, key=lambda item: item.from_sequence_order)
        ],
        "selected_place_ids": [
            stop.place_id
            for stop in sorted(stops, key=lambda item: item.sequence_order)
            if stop.place_id is not None
        ],
        "unselected_candidates": list(run.candidate_diagnostics_json or []),
        "rule_results": list(run.rule_results_json or []),
        "warnings": list(run.warnings_json or []),
        "alternatives": list(run.alternatives_json or []),
    }


def latest_accepted_run(session: Session, trip: Trip) -> SolveRun | None:
    run_id = trip.accepted_run_id
    if run_id is None:
        return None
    return session.get(SolveRun, run_id)


def serialize_workspace(session: Session, trip: Trip) -> dict:
    latest_run = latest_accepted_run(session, trip)
    latest_payload = None
    if latest_run is not None:
        stops = (
            session.query(SolveStop)
            .filter(SolveStop.solve_run_id == latest_run.id)
            .order_by(SolveStop.sequence_order.asc())
            .all()
        )
        route_legs = (
            session.query(SolveRouteLeg)
            .filter(SolveRouteLeg.solve_run_id == latest_run.id)
            .order_by(SolveRouteLeg.from_sequence_order.asc())
            .all()
        )
        latest_payload = serialize_solve_run(latest_run, stops=stops, route_legs=route_legs)
    return {
        "trip": serialize_trip_detail(trip),
        "workspace_version": trip.workspace_version,
        "candidates": [serialize_candidate(candidate) for candidate in trip.candidates],
        "rules": [serialize_rule(rule) for rule in trip.rules],
        "latest_accepted_run": latest_payload,
        "planning_summary": {
            "updated_at": datetime.now().isoformat(),
            "candidate_count": len(trip.candidates),
            "rule_count": len(trip.rules),
        },
    }
