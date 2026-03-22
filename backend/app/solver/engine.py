from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.errors import RequestContractError


PRIORITY_WEIGHT = {
    "must": 1000,
    "high": 120,
    "normal": 60,
    "low": 20,
    "backup": 5,
}


@dataclass(slots=True)
class PlannerPlace:
    id: int
    name: str
    lat: float
    lng: float
    source: str
    category: str | None
    tags: list[str]
    traits: list[str]
    stay_min_minutes: int
    stay_preferred_minutes: int
    stay_max_minutes: int
    price_band: str | None
    rating: float | None
    availability: list[dict[str, Any]]


@dataclass(slots=True)
class PlannerCandidate:
    id: int
    place: PlannerPlace
    candidate_state: str
    priority: str
    locked_in: bool
    locked_out: bool
    utility_override: int | None
    stay_override_min: int | None
    stay_override_preferred: int | None
    stay_override_max: int | None
    arrive_after_min: int | None
    arrive_before_min: int | None
    depart_after_min: int | None
    depart_before_min: int | None
    manual_order_hint: int | None
    user_note: str | None


@dataclass(slots=True)
class PlannerRule:
    id: int
    rule_kind: str
    scope: str
    mode: str
    weight: float | None
    target_kind: str
    target_payload: dict[str, Any]
    operator: str
    parameters: dict[str, Any]
    carry_forward_strategy: str
    label: str
    description: str | None


@dataclass(slots=True)
class PlannerTrip:
    id: int
    title: str
    plan_date: Any
    timezone: str
    origin_label: str
    origin_lat: float
    origin_lng: float
    destination_label: str
    destination_lat: float
    destination_lng: float
    departure_window_start_min: int
    departure_window_end_min: int
    end_constraint_kind: str
    end_constraint_minute_of_day: int
    context_weather: str | None
    context_traffic_profile: str | None


@dataclass(slots=True)
class PlannerResult:
    summary: dict[str, Any]
    stops: list[dict[str, Any]]
    selected_place_ids: list[int]
    route_place_ids: list[int]
    rule_results: list[dict[str, Any]]
    unselected_candidates: list[dict[str, Any]]
    warnings: list[str]
    alternatives: list[dict[str, Any]]
    departure_minutes: list[int]


def _matches_target(
    place: PlannerPlace,
    target_kind: str,
    target_payload: dict[str, Any],
    trip: PlannerTrip,
) -> bool:
    value = target_payload.get("value")
    if target_kind == "trip":
        return True
    if target_kind == "place":
        return value == place.id
    if target_kind == "tag":
        return isinstance(value, str) and value in place.tags
    if target_kind == "trait":
        return isinstance(value, str) and value in place.traits
    if target_kind == "category":
        return isinstance(value, str) and value == place.category
    if target_kind == "source":
        return isinstance(value, str) and value == place.source
    if target_kind == "price_band":
        return isinstance(value, str) and value == place.price_band
    if target_kind == "rating":
        threshold = target_payload.get("min")
        return isinstance(threshold, (int, float)) and (place.rating or 0) >= float(threshold)
    if target_kind == "place_pair":
        return True
    if target_kind == "distance_from_origin":
        radius_m = target_payload.get("radius_m")
        if not isinstance(radius_m, (int, float)):
            return False
        return ((place.lat - trip.origin_lat) ** 2 + (place.lng - trip.origin_lng) ** 2) ** 0.5 <= float(radius_m) / 100000
    if target_kind == "distance_from_destination":
        radius_m = target_payload.get("radius_m")
        if not isinstance(radius_m, (int, float)):
            return False
        return ((place.lat - trip.destination_lat) ** 2 + (place.lng - trip.destination_lng) ** 2) ** 0.5 <= float(radius_m) / 100000
    return False


def _current_availability(place: PlannerPlace, weekday: int) -> dict[str, Any] | None:
    direct = next((rule for rule in place.availability if rule.get("weekday") == weekday), None)
    if direct is not None:
        return direct
    return next((rule for rule in place.availability if rule.get("weekday") is None), None)


def _stay_minutes(candidate: PlannerCandidate) -> int:
    return (
        candidate.stay_override_preferred
        or candidate.place.stay_preferred_minutes
        or candidate.stay_override_min
        or candidate.place.stay_min_minutes
    )


def _base_score(candidate: PlannerCandidate, rules: list[PlannerRule], trip: PlannerTrip) -> float:
    score = PRIORITY_WEIGHT.get(candidate.priority, 40)
    if candidate.locked_in:
        score += 500
    if candidate.utility_override is not None:
        score += candidate.utility_override
    if candidate.place.rating is not None:
        score += candidate.place.rating * 10
    if "scenic" in candidate.place.tags:
        score += 8
    for rule in rules:
        if rule.rule_kind != "preference_match":
            continue
        if not _matches_target(candidate.place, rule.target_kind, rule.target_payload, trip):
            continue
        if rule.operator == "prefer":
            score += float(rule.weight or 0)
        elif rule.operator == "avoid":
            score -= float(rule.weight or 0)
    return score


def _sort_candidates(
    candidates: list[PlannerCandidate],
    rules: list[PlannerRule],
    trip: PlannerTrip,
    draft_order_edits: list[int],
) -> list[PlannerCandidate]:
    explicit_order = {place_id: index for index, place_id in enumerate(draft_order_edits)}
    return sorted(
        candidates,
        key=lambda candidate: (
            candidate.place.id not in explicit_order,
            explicit_order.get(candidate.place.id, candidate.manual_order_hint or 10_000),
            -(1 if candidate.locked_in else 0),
            -(PRIORITY_WEIGHT.get(candidate.priority, 40)),
            -_base_score(candidate, rules, trip),
            candidate.id,
        ),
    )


def _hard_excluded(candidate: PlannerCandidate, rules: list[PlannerRule], trip: PlannerTrip) -> bool:
    if candidate.candidate_state != "active" or candidate.locked_out:
        return True
    for rule in rules:
        if rule.mode != "hard":
            continue
        if rule.rule_kind == "selection_exclude" and _matches_target(
            candidate.place, rule.target_kind, rule.target_payload, trip
        ):
            return True
        if (
            rule.rule_kind == "context_filter"
            and rule.operator == "exclude"
            and _matches_target(candidate.place, rule.target_kind, rule.target_payload, trip)
            and trip.context_weather == rule.parameters.get("context_value")
        ):
            return True
    return False


def _selection_count_required(
    candidates: list[PlannerCandidate],
    rules: list[PlannerRule],
    trip: PlannerTrip,
) -> list[PlannerCandidate]:
    required: list[PlannerCandidate] = [candidate for candidate in candidates if candidate.locked_in or candidate.priority == "must"]
    for rule in rules:
        if rule.rule_kind != "selection_count" or rule.mode != "hard":
            continue
        if rule.operator != "include":
            continue
        exact_count = rule.parameters.get("exact_count")
        min_count = exact_count if isinstance(exact_count, int) else rule.parameters.get("min_count", 0)
        matching = [
            candidate
            for candidate in candidates
            if _matches_target(candidate.place, rule.target_kind, rule.target_payload, trip)
        ]
        if len(matching) < int(min_count):
            raise RequestContractError(
                "SOLVE_INFEASIBLE",
                "A hard selection rule could not be satisfied.",
                details={"rule_id": rule.id},
                status_code=409,
            )
        required.extend(matching[: int(min_count)])
    deduped: dict[int, PlannerCandidate] = {candidate.place.id: candidate for candidate in required}
    return list(deduped.values())


def _apply_order_constraints(place_ids: list[int], rules: list[PlannerRule]) -> list[int]:
    ordered = list(place_ids)
    for rule in rules:
        if rule.rule_kind != "order_dependency":
            continue
        target = rule.target_payload
        first_place_id = target.get("first_place_id")
        second_place_id = target.get("second_place_id")
        if (
            not isinstance(first_place_id, int)
            or not isinstance(second_place_id, int)
            or first_place_id not in ordered
            or second_place_id not in ordered
        ):
            continue
        first_index = ordered.index(first_place_id)
        second_index = ordered.index(second_place_id)
        if rule.operator == "require_before" and first_index > second_index:
            ordered[first_index], ordered[second_index] = ordered[second_index], ordered[first_index]
        if rule.operator == "require_after" and first_index < second_index:
            ordered[first_index], ordered[second_index] = ordered[second_index], ordered[first_index]
    return ordered


def _schedule(
    *,
    trip: PlannerTrip,
    ordered_candidates: list[PlannerCandidate],
    matrix_node_ids: list[str],
    matrix: list[list[int]],
) -> tuple[list[dict[str, Any]], list[int]]:
    node_index = {node_id: index for index, node_id in enumerate(matrix_node_ids)}
    current_node = "origin"
    current_minute = trip.departure_window_start_min
    stops: list[dict[str, Any]] = [
        {
            "sequence_order": 0,
            "node_kind": "origin",
            "place_id": None,
            "label": trip.origin_label,
            "lat": trip.origin_lat,
            "lng": trip.origin_lng,
            "arrival_min": current_minute,
            "departure_min": current_minute,
            "stay_min": 0,
            "leg_from_prev_min": None,
            "status": "planned",
        }
    ]
    departure_minutes: list[int] = [current_minute]
    sequence_order = 1
    for candidate in ordered_candidates:
        leg_min = matrix[node_index[current_node]][node_index[str(candidate.place.id)]]
        arrival_min = current_minute + leg_min
        availability = _current_availability(candidate.place, trip.plan_date.weekday())
        if availability is None or availability.get("closed_flag"):
            raise RequestContractError(
                "SOLVE_INFEASIBLE",
                "A selected place is not available on the trip date.",
                details={"candidate_id": candidate.id},
                status_code=409,
            )
        arrival_min = max(arrival_min, int(availability["open_minute"]))
        if candidate.arrive_after_min is not None:
            arrival_min = max(arrival_min, candidate.arrive_after_min)
        stay_min = _stay_minutes(candidate)
        departure_min = arrival_min + stay_min
        if candidate.arrive_before_min is not None and arrival_min > candidate.arrive_before_min:
            raise RequestContractError(
                "SOLVE_INFEASIBLE",
                "A candidate arrival preference could not be satisfied.",
                details={"candidate_id": candidate.id},
                status_code=409,
            )
        if candidate.depart_before_min is not None and departure_min > candidate.depart_before_min:
            raise RequestContractError(
                "SOLVE_INFEASIBLE",
                "A candidate departure preference could not be satisfied.",
                details={"candidate_id": candidate.id},
                status_code=409,
            )
        if departure_min > int(availability["close_minute"]):
            raise RequestContractError(
                "SOLVE_INFEASIBLE",
                "A selected place would be visited after closing time.",
                details={"candidate_id": candidate.id},
                status_code=409,
            )
        last_admission = availability.get("last_admission_minute")
        if isinstance(last_admission, int) and arrival_min > last_admission:
            raise RequestContractError(
                "SOLVE_INFEASIBLE",
                "A selected place would be reached after last admission.",
                details={"candidate_id": candidate.id},
                status_code=409,
            )
        stops.append(
            {
                "sequence_order": sequence_order,
                "node_kind": "place",
                "place_id": candidate.place.id,
                "label": candidate.place.name,
                "lat": candidate.place.lat,
                "lng": candidate.place.lng,
                "arrival_min": arrival_min,
                "departure_min": departure_min,
                "stay_min": stay_min,
                "leg_from_prev_min": leg_min,
                "status": "planned",
            }
        )
        departure_minutes.append(departure_min)
        current_minute = departure_min
        current_node = str(candidate.place.id)
        sequence_order += 1
    final_leg = matrix[node_index[current_node]][node_index["destination"]]
    end_arrival = current_minute + final_leg
    if trip.end_constraint_kind == "arrive_by" and end_arrival > trip.end_constraint_minute_of_day:
        raise RequestContractError(
            "SOLVE_INFEASIBLE",
            "The route would arrive after the trip end constraint.",
            details={"end_arrival": end_arrival},
            status_code=409,
        )
    stops.append(
        {
            "sequence_order": sequence_order,
            "node_kind": "destination",
            "place_id": None,
            "label": trip.destination_label,
            "lat": trip.destination_lat,
            "lng": trip.destination_lng,
            "arrival_min": end_arrival,
            "departure_min": end_arrival,
            "stay_min": 0,
            "leg_from_prev_min": final_leg,
            "status": "planned",
        }
    )
    return stops, departure_minutes


def _rule_results(
    *,
    rules: list[PlannerRule],
    selected_candidates: list[PlannerCandidate],
    unselected_candidates: list[PlannerCandidate],
    stops: list[dict[str, Any]],
    trip: PlannerTrip,
) -> list[dict[str, Any]]:
    selected_by_place = {candidate.place.id: candidate for candidate in selected_candidates}
    stop_by_place = {stop["place_id"]: stop for stop in stops if stop["place_id"] is not None}
    results: list[dict[str, Any]] = []
    for rule in rules:
        status = "satisfied"
        explanation = "Rule satisfied."
        score_impact = 0.0
        matching_selected = [
            candidate for candidate in selected_candidates
            if _matches_target(candidate.place, rule.target_kind, rule.target_payload, trip)
        ]
        if rule.rule_kind == "selection_count":
            exact_count = rule.parameters.get("exact_count")
            min_count = exact_count if isinstance(exact_count, int) else rule.parameters.get("min_count")
            max_count = exact_count if isinstance(exact_count, int) else rule.parameters.get("max_count")
            count = len(matching_selected)
            if min_count is not None and count < int(min_count):
                status = "violated"
                explanation = f"Required at least {min_count} matching places."
            if max_count is not None and count > int(max_count):
                status = "violated"
                explanation = f"Allowed at most {max_count} matching places."
        elif rule.rule_kind == "selection_exclude":
            if matching_selected:
                status = "violated"
                explanation = "An excluded place was still selected."
        elif rule.rule_kind == "preference_match":
            if rule.operator == "prefer":
                score_impact = float(rule.weight or 0) * len(matching_selected)
                explanation = f"Selected {len(matching_selected)} preferred places."
            else:
                score_impact = -float(rule.weight or 0) * len(matching_selected)
                explanation = f"Selected {len(matching_selected)} avoided places."
                if matching_selected:
                    status = "violated"
        elif rule.rule_kind == "order_dependency":
            payload = rule.target_payload
            first_place_id = payload.get("first_place_id")
            second_place_id = payload.get("second_place_id")
            if (
                isinstance(first_place_id, int)
                and isinstance(second_place_id, int)
                and first_place_id in stop_by_place
                and second_place_id in stop_by_place
            ):
                first_order = stop_by_place[first_place_id]["sequence_order"]
                second_order = stop_by_place[second_place_id]["sequence_order"]
                if rule.operator == "require_before" and first_order >= second_order:
                    status = "violated"
                    explanation = "Required order was not satisfied."
                elif rule.operator == "require_after" and first_order <= second_order:
                    status = "violated"
                    explanation = "Required order was not satisfied."
                else:
                    explanation = "Required order was satisfied."
        elif rule.rule_kind == "arrival_window":
            value = rule.target_payload.get("value")
            if isinstance(value, int) and value in stop_by_place:
                stop = stop_by_place[value]
                after = int(rule.parameters["arrive_after_min"])
                before = int(rule.parameters["arrive_before_min"])
                if not (after <= stop["arrival_min"] <= before):
                    status = "violated"
                    explanation = "Arrival was outside the requested window."
                else:
                    explanation = "Arrival was inside the requested window."
        elif rule.rule_kind == "stay_duration":
            value = rule.target_payload.get("value")
            if isinstance(value, int) and value in stop_by_place:
                stop = stop_by_place[value]
                min_minutes = rule.parameters.get("min_minutes")
                max_minutes = rule.parameters.get("max_minutes")
                preferred_minutes = rule.parameters.get("preferred_minutes")
                if min_minutes is not None and stop["stay_min"] < int(min_minutes):
                    status = "violated"
                    explanation = "Stay was shorter than requested."
                elif max_minutes is not None and stop["stay_min"] > int(max_minutes):
                    status = "violated"
                    explanation = "Stay was longer than requested."
                elif preferred_minutes is not None:
                    score_impact = -abs(stop["stay_min"] - int(preferred_minutes))
                    explanation = "Stay duration was scored against the preferred length."
        elif rule.rule_kind == "continuous_travel_limit":
            max_minutes = int(rule.parameters["max_minutes"])
            longest_leg = max(stop["leg_from_prev_min"] or 0 for stop in stops)
            if longest_leg > max_minutes:
                status = "violated"
                explanation = "A route leg exceeded the continuous travel limit."
            else:
                explanation = "All route legs stayed inside the travel limit."
        elif rule.rule_kind == "context_filter":
            context_matches = trip.context_weather == rule.parameters.get("context_value")
            if context_matches and matching_selected and rule.operator in {"exclude", "avoid"}:
                status = "violated" if rule.operator == "exclude" else "ignored"
                explanation = "Selected places conflict with the active context filter."
            else:
                explanation = "Context filter did not block the selected route."
        results.append(
            {
                "rule_id": rule.id,
                "status": status,
                "score_impact": score_impact,
                "explanation": explanation,
            }
        )
    return results


def _candidate_diagnostics(
    *,
    selected_candidates: list[PlannerCandidate],
    all_candidates: list[PlannerCandidate],
    rules: list[PlannerRule],
    trip: PlannerTrip,
) -> list[dict[str, Any]]:
    selected_ids = {candidate.id for candidate in selected_candidates}
    diagnostics: list[dict[str, Any]] = []
    for candidate in all_candidates:
        if candidate.id in selected_ids:
            continue
        blocking_rule_ids = [
            rule.id
            for rule in rules
            if rule.mode == "hard"
            and rule.rule_kind in {"selection_exclude", "context_filter"}
            and _matches_target(candidate.place, rule.target_kind, rule.target_payload, trip)
        ]
        explanation = (
            "Excluded by a hard rule." if blocking_rule_ids else "Dropped to keep the route feasible."
        )
        diagnostics.append(
            {
                "candidate_id": candidate.id,
                "status": "unselected",
                "explanation": explanation,
                "blocking_rule_ids": blocking_rule_ids,
            }
        )
    return diagnostics


def plan_trip(
    *,
    trip: PlannerTrip,
    candidates: list[PlannerCandidate],
    rules: list[PlannerRule],
    matrix_node_ids: list[str],
    matrix: list[list[int]],
    draft_order_edits: list[int],
) -> PlannerResult:
    filtered_candidates = [candidate for candidate in candidates if not _hard_excluded(candidate, rules, trip)]
    required_candidates = _selection_count_required(filtered_candidates, rules, trip)
    sorted_candidates = _sort_candidates(filtered_candidates, rules, trip, draft_order_edits)
    selected: dict[int, PlannerCandidate] = {candidate.place.id: candidate for candidate in required_candidates}
    for candidate in sorted_candidates:
        selected.setdefault(candidate.place.id, candidate)
    ordered_place_ids = _apply_order_constraints(list(selected.keys()), rules)
    ordered_candidates = [selected[place_id] for place_id in ordered_place_ids]
    stops, departure_minutes = _schedule(
        trip=trip,
        ordered_candidates=ordered_candidates,
        matrix_node_ids=matrix_node_ids,
        matrix=matrix,
    )
    rule_results = _rule_results(
        rules=rules,
        selected_candidates=ordered_candidates,
        unselected_candidates=[candidate for candidate in candidates if candidate.place.id not in ordered_place_ids],
        stops=stops,
        trip=trip,
    )
    warnings = [result["explanation"] for result in rule_results if result["status"] in {"violated", "ignored"}]
    selected_place_ids = [candidate.place.id for candidate in ordered_candidates]
    total_drive_minutes = sum(stop["leg_from_prev_min"] or 0 for stop in stops)
    total_stay_minutes = sum(stop["stay_min"] for stop in stops)
    alternatives = [
        {
            "label": candidate.place.name,
            "description": "未選択候補として残っています。",
            "candidate_id": candidate.id,
            "place_id": candidate.place.id,
        }
        for candidate in _sort_candidates(
            [candidate for candidate in candidates if candidate.place.id not in selected_place_ids],
            rules,
            trip,
            [],
        )[:3]
    ]
    return PlannerResult(
        summary={
            "feasible": True,
            "score": round(sum(_base_score(candidate, rules, trip) for candidate in ordered_candidates), 2),
            "total_drive_minutes": total_drive_minutes,
            "total_stay_minutes": total_stay_minutes,
            "total_distance_meters": 0,
            "start_time_min": stops[0]["departure_min"],
            "end_time_min": stops[-1]["arrival_min"],
        },
        stops=stops,
        selected_place_ids=selected_place_ids,
        route_place_ids=selected_place_ids,
        rule_results=rule_results,
        unselected_candidates=_candidate_diagnostics(
            selected_candidates=ordered_candidates,
            all_candidates=candidates,
            rules=rules,
            trip=trip,
        ),
        warnings=warnings,
        alternatives=alternatives,
        departure_minutes=departure_minutes,
    )
