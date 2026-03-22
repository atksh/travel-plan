from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.errors import RequestContractError
from app.models.place import Place
from app.models.rule import TripRule
from app.models.solve import SolveRouteLeg, SolveRun, SolveStop
from app.models.trip import Trip, TripCandidate
from app.services.routing_costs import RouteNode, build_route_legs, build_route_matrix
from app.solver import PlannerCandidate, PlannerPlace, PlannerRule, PlannerTrip, plan_trip


def get_trip_or_error(session: Session, trip_id: int) -> Trip:
    trip = session.get(Trip, trip_id)
    if trip is None:
        raise RequestContractError("TRIP_NOT_FOUND", "Trip not found.", status_code=404)
    return trip


def _candidate_patch_map(draft_candidate_patches: list[dict]) -> dict[int, dict]:
    patches: dict[int, dict] = {}
    for patch in draft_candidate_patches:
        candidate_id = patch.get("candidate_id")
        if isinstance(candidate_id, int):
            patches[candidate_id] = patch
    return patches


def _build_candidate(
    candidate: TripCandidate,
    patch: dict | None = None,
) -> PlannerCandidate:
    patch = patch or {}
    place = candidate.place
    if place.visit_profile is None:
        raise RequestContractError(
            "PLACE_NOT_FOUND",
            "A candidate place is missing its visit profile.",
            details={"place_id": place.id},
            status_code=409,
        )
    return PlannerCandidate(
        id=candidate.id,
        place=PlannerPlace(
            id=place.id,
            name=place.name,
            lat=place.lat,
            lng=place.lng,
            source=place.source,
            category=place.category,
            tags=list(place.tags_json or []),
            traits=list(place.traits_json or []),
            stay_min_minutes=place.visit_profile.stay_min_minutes,
            stay_preferred_minutes=place.visit_profile.stay_preferred_minutes,
            stay_max_minutes=place.visit_profile.stay_max_minutes,
            price_band=place.visit_profile.price_band,
            rating=place.visit_profile.rating,
            availability=[
                {
                    "weekday": rule.weekday,
                    "open_minute": rule.open_minute,
                    "close_minute": rule.close_minute,
                    "last_admission_minute": rule.last_admission_minute,
                    "closed_flag": rule.closed_flag,
                }
                for rule in place.availability_rules
            ],
        ),
        candidate_state=patch.get("candidate_state", candidate.candidate_state),
        priority=patch.get("priority", candidate.priority),
        locked_in=patch.get("locked_in", candidate.locked_in),
        locked_out=patch.get("locked_out", candidate.locked_out),
        utility_override=patch.get("utility_override", candidate.utility_override),
        stay_override_min=(patch.get("stay_override") or {}).get("min", candidate.stay_override_min),
        stay_override_preferred=(patch.get("stay_override") or {}).get(
            "preferred", candidate.stay_override_preferred
        ),
        stay_override_max=(patch.get("stay_override") or {}).get("max", candidate.stay_override_max),
        arrive_after_min=(patch.get("time_preference") or {}).get("arrive_after_min", candidate.arrive_after_min),
        arrive_before_min=(patch.get("time_preference") or {}).get("arrive_before_min", candidate.arrive_before_min),
        depart_after_min=(patch.get("time_preference") or {}).get("depart_after_min", candidate.depart_after_min),
        depart_before_min=(patch.get("time_preference") or {}).get("depart_before_min", candidate.depart_before_min),
        manual_order_hint=patch.get("manual_order_hint", candidate.manual_order_hint),
        user_note=patch.get("user_note", candidate.user_note),
    )


def _build_rule(rule: TripRule) -> PlannerRule:
    return PlannerRule(
        id=rule.id,
        rule_kind=rule.rule_kind,
        scope=rule.scope,
        mode=rule.mode,
        weight=rule.weight,
        target_kind=rule.target_kind,
        target_payload=dict(rule.target_payload_json or {}),
        operator=rule.operator,
        parameters=dict(rule.parameters_json or {}),
        carry_forward_strategy=rule.carry_forward_strategy,
        label=rule.label,
        description=rule.description,
    )


def _apply_draft_rule_patches(rules: list[PlannerRule], draft_rule_patches: list[dict]) -> list[PlannerRule]:
    next_rules = deepcopy(rules)
    rule_map = {rule.id: rule for rule in next_rules}
    for patch in draft_rule_patches:
        action = patch.get("action", "update")
        if action == "delete" and isinstance(patch.get("rule_id"), int):
            rule_map.pop(patch["rule_id"], None)
            continue
        if action == "create":
            temp_rule_id = int(patch.get("rule_id") or -(len(rule_map) + 1))
            rule_map[temp_rule_id] = PlannerRule(
                id=temp_rule_id,
                rule_kind=patch["rule_kind"],
                scope=patch["scope"],
                mode=patch["mode"],
                weight=patch.get("weight"),
                target_kind=patch["target"]["kind"],
                target_payload={
                    "value": patch["target"].get("value"),
                    **(patch["target"].get("data") or {}),
                },
                operator=patch["operator"],
                parameters=dict(patch.get("parameters") or {}),
                carry_forward_strategy=patch["carry_forward_strategy"],
                label=patch["label"],
                description=patch.get("description"),
            )
            continue
        rule_id = patch.get("rule_id")
        if not isinstance(rule_id, int) or rule_id not in rule_map:
            continue
        existing = rule_map[rule_id]
        if "mode" in patch:
            existing.mode = patch["mode"]
        if "weight" in patch:
            existing.weight = patch["weight"]
        if "operator" in patch:
            existing.operator = patch["operator"]
        if "parameters" in patch:
            existing.parameters = dict(patch["parameters"] or {})
        if "label" in patch:
            existing.label = patch["label"]
        if "description" in patch:
            existing.description = patch["description"]
        if "target" in patch:
            existing.target_kind = patch["target"]["kind"]
            existing.target_payload = {
                "value": patch["target"].get("value"),
                **(patch["target"].get("data") or {}),
            }
    return list(rule_map.values())


async def generate_solve_payload(
    session: Session,
    *,
    trip: Trip,
    draft_candidate_patches: list[dict] | None = None,
    draft_rule_patches: list[dict] | None = None,
    draft_order_edits: list[int] | None = None,
    origin_override: dict | None = None,
    departure_override_min: int | None = None,
    destination_override: dict | None = None,
) -> dict:
    trip_ctx = PlannerTrip(
        id=trip.id,
        title=trip.title,
        plan_date=trip.plan_date,
        timezone=trip.timezone,
        origin_label=(origin_override or {}).get("label", trip.origin_label),
        origin_lat=(origin_override or {}).get("lat", trip.origin_lat),
        origin_lng=(origin_override or {}).get("lng", trip.origin_lng),
        destination_label=(destination_override or {}).get("label", trip.destination_label),
        destination_lat=(destination_override or {}).get("lat", trip.destination_lat),
        destination_lng=(destination_override or {}).get("lng", trip.destination_lng),
        departure_window_start_min=(
            trip.departure_window_start_min if departure_override_min is None else departure_override_min
        ),
        departure_window_end_min=(
            trip.departure_window_end_min if departure_override_min is None else departure_override_min
        ),
        end_constraint_kind=trip.end_constraint_kind,
        end_constraint_minute_of_day=trip.end_constraint_minute_of_day,
        context_weather=trip.context_weather,
        context_traffic_profile=trip.context_traffic_profile,
    )
    candidate_patches = _candidate_patch_map(draft_candidate_patches or [])
    planner_candidates = [_build_candidate(candidate, candidate_patches.get(candidate.id)) for candidate in trip.candidates]
    planner_rules = _apply_draft_rule_patches([_build_rule(rule) for rule in trip.rules], draft_rule_patches or [])
    matrix_nodes = [
        RouteNode("origin", trip_ctx.origin_lat, trip_ctx.origin_lng),
        *[RouteNode(str(candidate.place.id), candidate.place.lat, candidate.place.lng) for candidate in planner_candidates],
        RouteNode("destination", trip_ctx.destination_lat, trip_ctx.destination_lng),
    ]
    matrix = await build_route_matrix(
        nodes=matrix_nodes,
        plan_date=trip.plan_date,
        departure_min=trip_ctx.departure_window_start_min,
        traffic_profile=trip.context_traffic_profile,
    )
    planner_result = plan_trip(
        trip=trip_ctx,
        candidates=planner_candidates,
        rules=planner_rules,
        matrix_node_ids=[node.node_id for node in matrix_nodes],
        matrix=matrix,
        draft_order_edits=draft_order_edits or [],
    )
    candidate_by_place_id = {candidate.place.id: candidate for candidate in planner_candidates}
    coordinates = [
        (trip_ctx.origin_lat, trip_ctx.origin_lng),
        *[
            (candidate_by_place_id[place_id].place.lat, candidate_by_place_id[place_id].place.lng)
            for place_id in planner_result.route_place_ids
        ],
        (trip_ctx.destination_lat, trip_ctx.destination_lng),
    ]
    route_legs = await build_route_legs(
        coordinates=coordinates,
        plan_date=trip.plan_date,
        departure_minutes=planner_result.departure_minutes,
        traffic_profile=trip.context_traffic_profile,
    )
    planner_result.summary["total_distance_meters"] = sum(leg.distance_meters or 0 for leg in route_legs)
    return {
        "summary": planner_result.summary,
        "stops": planner_result.stops,
        "route_legs": [
            {
                "from_sequence_order": index,
                "to_sequence_order": index + 1,
                "duration_minutes": leg.duration_minutes,
                "distance_meters": leg.distance_meters,
                "encoded_polyline": leg.polyline,
            }
            for index, leg in enumerate(route_legs)
        ],
        "selected_place_ids": planner_result.selected_place_ids,
        "unselected_candidates": planner_result.unselected_candidates,
        "rule_results": planner_result.rule_results,
        "warnings": planner_result.warnings,
        "alternatives": planner_result.alternatives,
    }


def persist_solve_run(
    session: Session,
    *,
    trip: Trip,
    run_kind: str,
    solve_payload: dict,
    based_on_preview_id: str | None = None,
) -> SolveRun:
    run = SolveRun(
        trip_id=trip.id,
        run_kind=run_kind,
        accepted_at=datetime.now(timezone.utc),
        workspace_version=trip.workspace_version,
        based_on_preview_id=based_on_preview_id,
        summary_json=dict(solve_payload["summary"]),
        warnings_json=list(solve_payload["warnings"]),
        rule_results_json=list(solve_payload["rule_results"]),
        candidate_diagnostics_json=list(solve_payload["unselected_candidates"]),
        alternatives_json=list(solve_payload["alternatives"]),
    )
    session.add(run)
    session.flush()
    for stop in solve_payload["stops"]:
        session.add(
            SolveStop(
                solve_run_id=run.id,
                sequence_order=stop["sequence_order"],
                node_kind=stop["node_kind"],
                place_id=stop["place_id"],
                label=stop["label"],
                lat=stop["lat"],
                lng=stop["lng"],
                arrival_min=stop["arrival_min"],
                departure_min=stop["departure_min"],
                stay_min=stop["stay_min"],
                leg_from_prev_min=stop["leg_from_prev_min"],
                status=stop["status"],
            )
        )
    for route_leg in solve_payload["route_legs"]:
        session.add(
            SolveRouteLeg(
                solve_run_id=run.id,
                from_sequence_order=route_leg["from_sequence_order"],
                to_sequence_order=route_leg["to_sequence_order"],
                duration_minutes=route_leg["duration_minutes"],
                distance_meters=route_leg["distance_meters"],
                encoded_polyline=route_leg["encoded_polyline"],
            )
        )
    session.flush()
    return run
