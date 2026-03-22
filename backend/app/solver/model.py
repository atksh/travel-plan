"""Core trip solver using OR-Tools MIP with a heuristic fallback."""

from __future__ import annotations

import itertools
import time
from dataclasses import dataclass, field
from datetime import date

from ortools.linear_solver import pywraplp
from sqlalchemy.orm import Session

from app.models.poi import PoiDependencyRule, PoiMaster
from app.services.geo import estimate_drive_minutes

START_NODE = -1
END_NODE = -2
MAX_HEURISTIC_NODES = 12
STOP_PENALTY = 1.0
LATE_MEAL_PENALTY = 0.08
WAIT_RISK_PENALTY = 0.1
CONTINUOUS_DRIVE_PENALTY = 0.06
PACE_SHORTLIST_LIMITS = {"relaxed": 12, "balanced": 15, "packed": 18}
PACE_STOP_PENALTIES = {"relaxed": 1.75, "balanced": STOP_PENALTY, "packed": 0.5}
PACE_DRIVE_MULTIPLIERS = {"relaxed": 1.25, "balanced": 1.0, "packed": 0.85}
MEAL_REASON_CODES = (
    ("lunch", "no_lunch_candidate"),
    ("dinner", "no_dinner_candidate"),
    ("sweets", "no_sweets_candidate"),
)
CATEGORY_RANK = {
    "lunch": 10,
    "sightseeing_active": 20,
    "sightseeing_relax": 25,
    "sunset": 40,
    "sweets": 45,
    "healing": 50,
    "dinner": 60,
    "hub": 80,
}
OPTIONAL_CATEGORY_SET = {"lunch", "dinner", "sweets", "sunset"}


@dataclass
class SolverInput:
    origin_lat: float
    origin_lng: float
    dest_lat: float
    dest_lng: float
    departure_start_min: int
    departure_window_end_min: int
    return_deadline_min: int
    candidate_poi_ids: list[int]
    must_visit: set[int]
    driving_penalty_weight: float
    weather_mode: str
    plan_date: date | None = None
    excluded_poi_ids: set[int] = field(default_factory=set)
    utility_overrides: dict[int, int] = field(default_factory=dict)
    max_continuous_drive_minutes: int = 120
    preferred_lunch_tags: set[str] = field(default_factory=set)
    preferred_dinner_tags: set[str] = field(default_factory=set)
    must_have_cafe: bool = False
    satisfied_categories: set[str] = field(default_factory=set)
    cafe_requirement_already_met: bool = False
    budget_band: str | None = None
    pace_style: str = "balanced"
    matrix_node_ids: list[int] | None = None
    travel_matrix: list[list[int]] | None = None


@dataclass
class SolverResult:
    feasible: bool
    objective: float | None
    ordered_poi_ids: list[int]
    arrival_minutes: list[int | None]
    departure_minutes: list[int | None]
    leg_minutes: list[int | None]
    reason_codes: list[str]
    solve_ms: int
    start_departure_min: int | None = None


@dataclass
class PreparedSolverData:
    poi_ids: list[int]
    coords: dict[int, tuple[float, float]]
    open_window: dict[int, tuple[int, int]]
    stay_bounds: dict[int, tuple[int, int]]
    meal_window: dict[int, tuple[int | None, int | None]]
    last_admission: dict[int, int | None]
    utility: dict[int, int]
    category: dict[int, str]
    tags: dict[int, set[str]]
    price_band: dict[int, str | None]
    dependencies: list[tuple[int, int]]
    travel: dict[tuple[int, int], int]
    all_node_ids: list[int]
    reasons: list[str]


def _select_opening_window(
    poi: PoiMaster, plan_date: date | None
) -> tuple[int, int, int | None] | None:
    if not poi.opening_rules:
        return 0, 24 * 60, None

    generic_rule = next(
        (rule for rule in poi.opening_rules if rule.weekday is None),
        None,
    )
    chosen = generic_rule
    if plan_date is not None:
        weekday = plan_date.weekday()
        chosen = next(
            (rule for rule in poi.opening_rules if rule.weekday == weekday),
            generic_rule,
        )
    if chosen is None:
        return None
    return chosen.open_minute, chosen.close_minute, chosen.last_admission_minute


def pace_shortlist_max(pace_style: str) -> int:
    return PACE_SHORTLIST_LIMITS.get(pace_style, PACE_SHORTLIST_LIMITS["balanced"])


def _pace_stop_penalty(pace_style: str) -> float:
    return PACE_STOP_PENALTIES.get(pace_style, PACE_STOP_PENALTIES["balanced"])


def _pace_drive_penalty_multiplier(pace_style: str) -> float:
    return PACE_DRIVE_MULTIPLIERS.get(
        pace_style,
        PACE_DRIVE_MULTIPLIERS["balanced"],
    )


def _apply_pace_to_stay_bounds(
    stay_min: int,
    stay_max: int,
    pace_style: str,
) -> tuple[int, int]:
    mid_floor = (stay_min + stay_max) // 2
    mid_ceil = (stay_min + stay_max + 1) // 2
    if pace_style == "relaxed":
        return mid_ceil, stay_max
    if pace_style == "packed":
        return stay_min, max(stay_min, mid_floor)
    return stay_min, stay_max


def _tag_preference_bonus(
    category_name: str,
    tag_set: set[str],
    inp: SolverInput,
) -> int:
    preferred_tags: set[str] = set()
    if category_name == "lunch":
        preferred_tags = inp.preferred_lunch_tags
    elif category_name == "dinner":
        preferred_tags = inp.preferred_dinner_tags
    if not preferred_tags:
        return 0
    return min(6, 3 * len(tag_set & preferred_tags))


def _budget_preference_bonus(
    preferred_band: str | None,
    poi_band: str | None,
) -> int:
    if preferred_band is None or poi_band is None:
        return 0
    order = {"casual": 0, "moderate": 1, "premium": 2}
    if preferred_band not in order or poi_band not in order:
        return 0
    distance = abs(order[preferred_band] - order[poi_band])
    if distance == 0:
        return 2
    if distance == 1:
        return -2
    return -4


def _has_cafe_tag(tag_set: set[str]) -> bool:
    return "cafe" in tag_set


def _cafe_ids(data: PreparedSolverData) -> list[int]:
    return [
        poi_id for poi_id in data.poi_ids if _has_cafe_tag(data.tags.get(poi_id, set()))
    ]


def _is_category_required(inp: SolverInput, category_name: str) -> bool:
    if category_name == "sunset":
        return (
            inp.weather_mode != "rain"
            and category_name not in inp.satisfied_categories
        )
    return category_name not in inp.satisfied_categories


def _requires_additional_cafe(inp: SolverInput) -> bool:
    return inp.must_have_cafe and not inp.cafe_requirement_already_met


def _missing_required_category_codes(
    inp: SolverInput, data: PreparedSolverData
) -> list[str]:
    return _precheck_reason_codes(inp, data)


def _missing_must_visit_codes(
    inp: SolverInput,
    data: PreparedSolverData,
) -> list[str]:
    available_ids = set(data.poi_ids)
    return [
        f"must_visit_{poi_id}_not_candidate"
        for poi_id in sorted(inp.must_visit)
        if poi_id not in available_ids
    ]


def _precheck_reason_codes(
    inp: SolverInput,
    data: PreparedSolverData,
) -> list[str]:
    return _dedupe_codes(
        _required_reason_codes(inp, data, include_sunset=True, include_cafe=True),
        _missing_must_visit_codes(inp, data),
    )


def _effective_drive_penalty_weight(inp: SolverInput) -> float:
    return inp.driving_penalty_weight * _pace_drive_penalty_multiplier(inp.pace_style)


def _dedupe_codes(*groups: list[str]) -> list[str]:
    return list(dict.fromkeys(code for group in groups for code in group))


def _infeasible_result(reason_codes: list[str]) -> SolverResult:
    return SolverResult(
        feasible=False,
        objective=None,
        ordered_poi_ids=[],
        arrival_minutes=[],
        departure_minutes=[],
        leg_minutes=[],
        reason_codes=list(dict.fromkeys(reason_codes)),
        solve_ms=0,
    )


def _category_groups(data: PreparedSolverData) -> dict[str, list[int]]:
    return {
        category_name: _category_ids(data, category_name)
        for category_name in (*dict(MEAL_REASON_CODES), "sunset")
    }


def _required_reason_codes(
    inp: SolverInput,
    data: PreparedSolverData,
    *,
    include_sunset: bool = False,
    include_cafe: bool = False,
    groups: dict[str, list[int]] | None = None,
    cafe_ids: list[int] | None = None,
) -> list[str]:
    groups = _category_groups(data) if groups is None else groups
    missing = [
        reason_code
        for category_name, reason_code in MEAL_REASON_CODES
        if _is_category_required(inp, category_name) and not groups[category_name]
    ]
    if include_sunset and _is_category_required(inp, "sunset") and not groups["sunset"]:
        missing.append("no_sunset_candidate")
    if include_cafe and _requires_additional_cafe(inp):
        cafe_ids = _cafe_ids(data) if cafe_ids is None else cafe_ids
        if not cafe_ids:
            missing.append("no_cafe_candidate")
    return missing


def _has_wait_risk(data: PreparedSolverData, poi_id: int) -> bool:
    return "high_wait_risk" in data.tags.get(poi_id, set())


def _wait_risk_start(meal_start: int, meal_end: int) -> int:
    return max(meal_start, meal_end - 30)


def _visit_base_score(
    poi_id: int,
    inp: SolverInput,
    data: PreparedSolverData,
) -> float:
    return data.utility[poi_id] - (
        0.0 if poi_id in inp.must_visit else _pace_stop_penalty(inp.pace_style)
    ) - (2.0 if _has_wait_risk(data, poi_id) else 0.0)


def _travel_penalty(minutes: int, inp: SolverInput) -> float:
    penalty = _effective_drive_penalty_weight(inp) * minutes
    if minutes > inp.max_continuous_drive_minutes:
        penalty += CONTINUOUS_DRIVE_PENALTY * (
            minutes - inp.max_continuous_drive_minutes
        )
    return penalty


def _normalize_departure_window(
    inp: SolverInput,
    data: PreparedSolverData,
    result: SolverResult,
) -> SolverResult:
    if not result.feasible:
        return result

    max_shift = inp.departure_window_end_min - inp.departure_start_min
    if max_shift <= 0:
        result.start_departure_min = inp.departure_start_min
        return result

    end_idx = len(result.ordered_poi_ids)
    if end_idx < len(result.arrival_minutes):
        end_arrival = result.arrival_minutes[end_idx]
        if end_arrival is not None:
            max_shift = min(max_shift, inp.return_deadline_min - end_arrival)

    for idx, poi_id in enumerate(result.ordered_poi_ids):
        arrival = result.arrival_minutes[idx] if idx < len(result.arrival_minutes) else None
        departure = (
            result.departure_minutes[idx] if idx < len(result.departure_minutes) else None
        )
        _open_min, close_min = data.open_window[poi_id]
        _meal_start, meal_end = data.meal_window[poi_id]
        last_admission = data.last_admission[poi_id]
        if arrival is not None and meal_end is not None:
            max_shift = min(max_shift, meal_end - arrival)
        if arrival is not None and last_admission is not None:
            max_shift = min(max_shift, last_admission - arrival)
        if departure is not None:
            max_shift = min(max_shift, close_min - departure)

    shift = max(0, int(max_shift))
    result.start_departure_min = inp.departure_start_min + shift
    if shift == 0:
        return result

    result.arrival_minutes = [
        minute + shift if minute is not None else None
        for minute in result.arrival_minutes
    ]
    result.departure_minutes = [
        minute + shift if minute is not None else None
        for minute in result.departure_minutes
    ]
    return result


def _prepare_solver_data(session: Session, inp: SolverInput) -> PreparedSolverData:
    candidate_ids = []
    seen: set[int] = set()
    for poi_id in inp.candidate_poi_ids:
        if poi_id in (0, 99) or poi_id in inp.excluded_poi_ids or poi_id in seen:
            continue
        seen.add(poi_id)
        candidate_ids.append(poi_id)

    pois = session.query(PoiMaster).filter(PoiMaster.id.in_(candidate_ids)).all()
    poi_map = {poi.id: poi for poi in pois}
    coords = {
        START_NODE: (inp.origin_lat, inp.origin_lng),
        END_NODE: (inp.dest_lat, inp.dest_lng),
    }
    open_window: dict[int, tuple[int, int]] = {}
    stay_bounds: dict[int, tuple[int, int]] = {}
    meal_window: dict[int, tuple[int | None, int | None]] = {}
    last_admission: dict[int, int | None] = {}
    utility: dict[int, int] = {}
    category: dict[int, str] = {}
    tags: dict[int, set[str]] = {}
    price_band: dict[int, str | None] = {}
    reasons: list[str] = []

    poi_ids: list[int] = []
    for poi_id in candidate_ids:
        poi = poi_map.get(poi_id)
        if poi is None:
            reasons.append(f"missing_poi_{poi_id}")
            continue
        if poi.planning_profile is None:
            reasons.append(f"missing_profile_{poi_id}")
            continue
        opening_window = _select_opening_window(poi, inp.plan_date)
        if opening_window is None:
            continue
        poi_ids.append(poi_id)
        coords[poi_id] = (poi.lat, poi.lng)
        open_min, close_min, last_adm = opening_window
        open_window[poi_id] = (open_min, close_min)
        pace_min, pace_max = _apply_pace_to_stay_bounds(
            poi.planning_profile.stay_min_minutes,
            poi.planning_profile.stay_max_minutes,
            inp.pace_style,
        )
        stay_bounds[poi_id] = (
            pace_min,
            pace_max,
        )
        meal_window[poi_id] = (
            poi.planning_profile.meal_window_start_min,
            poi.planning_profile.meal_window_end_min,
        )
        last_admission[poi_id] = last_adm
        tag_set = {link.tag.slug for link in poi.tag_links}
        tags[poi_id] = tag_set
        price_band[poi_id] = poi.planning_profile.price_band
        base_utility = inp.utility_overrides.get(
            poi_id, poi.planning_profile.utility_default
        )
        base_utility += _tag_preference_bonus(poi.primary_category, tag_set, inp)
        base_utility += _budget_preference_bonus(
            inp.budget_band,
            poi.planning_profile.price_band,
        )
        utility[poi_id] = base_utility
        category[poi_id] = poi.primary_category

    dependency_rows = (
        session.query(PoiDependencyRule)
        .filter(PoiDependencyRule.if_visit_poi_id.in_(poi_ids))
        .all()
    )
    dependencies = [(row.if_visit_poi_id, row.require_poi_id) for row in dependency_rows]

    all_node_ids = [START_NODE] + poi_ids + [END_NODE]
    travel: dict[tuple[int, int], int] = {}
    matrix_index = {}
    if inp.matrix_node_ids is not None and inp.travel_matrix is not None:
        matrix_index = {node_id: idx for idx, node_id in enumerate(inp.matrix_node_ids)}

    for i in all_node_ids:
        for j in all_node_ids:
            if i == j:
                continue
            if i in matrix_index and j in matrix_index and inp.travel_matrix is not None:
                travel[(i, j)] = int(inp.travel_matrix[matrix_index[i]][matrix_index[j]])
                continue
            start_coord = coords[i]
            end_coord = coords[j]
            travel[(i, j)] = estimate_drive_minutes(
                start_coord[0],
                start_coord[1],
                end_coord[0],
                end_coord[1],
            )

    return PreparedSolverData(
        poi_ids=poi_ids,
        coords=coords,
        open_window=open_window,
        stay_bounds=stay_bounds,
        meal_window=meal_window,
        last_admission=last_admission,
        utility=utility,
        category=category,
        tags=tags,
        price_band=price_band,
        dependencies=dependencies,
        travel=travel,
        all_node_ids=all_node_ids,
        reasons=reasons,
    )


def _category_ids(data: PreparedSolverData, category_name: str) -> list[int]:
    return [poi_id for poi_id in data.poi_ids if data.category.get(poi_id) == category_name]


def _expand_dependency_closure(
    selected_ids: set[int],
    dependencies: list[tuple[int, int]],
    *,
    available_ids: set[int],
) -> set[int] | None:
    dependency_map: dict[int, set[int]] = {}
    for if_visit_poi_id, require_poi_id in dependencies:
        dependency_map.setdefault(if_visit_poi_id, set()).add(require_poi_id)

    closed = set(selected_ids)
    queue = list(selected_ids)
    while queue:
        poi_id = queue.pop()
        for require_poi_id in dependency_map.get(poi_id, set()):
            if require_poi_id not in available_ids:
                return None
            if require_poi_id in closed:
                continue
            closed.add(require_poi_id)
            queue.append(require_poi_id)
    return closed


def _diagnose_infeasibility(
    inp: SolverInput, data: PreparedSolverData
) -> list[str]:
    reasons = _dedupe_codes(
        data.reasons,
        _required_reason_codes(inp, data, include_sunset=True, include_cafe=True),
    )

    if inp.weather_mode == "rain":
        removed_outdoor = any(
            data.category.get(poi_id) in {"sightseeing_active", "sunset"}
            for poi_id in inp.candidate_poi_ids
            if poi_id not in data.poi_ids
        )
        if removed_outdoor:
            reasons.append("rain_mode_removed_outdoor_candidates")

    for poi_id in sorted(inp.must_visit):
        if poi_id not in data.poi_ids:
            reasons.append(f"must_visit_{poi_id}_not_candidate")
            continue
        open_min, close_min = data.open_window[poi_id]
        stay_min, _stay_max = data.stay_bounds[poi_id]
        meal_start, meal_end = data.meal_window[poi_id]
        earliest = inp.departure_start_min + data.travel[(START_NODE, poi_id)]
        if meal_start is not None:
            earliest = max(earliest, meal_start)
        else:
            earliest = max(earliest, open_min)
        latest_allowed = data.last_admission[poi_id]
        if latest_allowed is None:
            latest_allowed = close_min - stay_min
        if earliest > latest_allowed or earliest + stay_min > close_min:
            reasons.append(f"must_visit_{poi_id}_infeasible_after_{earliest:04d}")

    if not reasons:
        reasons.append("no_feasible_route")
    return list(dict.fromkeys(reasons))


def _choose_mip_solver() -> tuple[pywraplp.Solver | None, str]:
    scip = pywraplp.Solver.CreateSolver("SCIP")
    if scip is not None:
        return scip, "SCIP"
    cbc = pywraplp.Solver.CreateSolver("CBC")
    if cbc is not None:
        return cbc, "CBC"
    return None, "NONE"


def _solve_with_mip(inp: SolverInput, data: PreparedSolverData) -> tuple[int, SolverResult]:
    solver, backend = _choose_mip_solver()
    if solver is None:
        return pywraplp.Solver.NOT_SOLVED, SolverResult(
            feasible=False,
            objective=None,
            ordered_poi_ids=[],
            arrival_minutes=[],
            departure_minutes=[],
            leg_minutes=[],
            reason_codes=["no_mip_backend"],
            solve_ms=0,
        )

    big_m = max(inp.return_deadline_min + 24 * 60, 24 * 60 * 3)
    upper_bound = max(inp.return_deadline_min + 24 * 60, 24 * 60 * 2)
    solver.SetTimeLimit(5000)

    y = {poi_id: solver.BoolVar(f"y_{poi_id}") for poi_id in data.poi_ids}
    a = {poi_id: solver.IntVar(0, upper_bound, f"a_{poi_id}") for poi_id in data.poi_ids}
    a_end = solver.IntVar(0, upper_bound, "a_end")
    s = {poi_id: solver.IntVar(0, upper_bound, f"s_{poi_id}") for poi_id in data.poi_ids}

    x: dict[tuple[int, int], pywraplp.Variable] = {}
    for i in data.all_node_ids:
        if i == END_NODE:
            continue
        for j in data.all_node_ids:
            if i == j or j == START_NODE:
                continue
            x[(i, j)] = solver.BoolVar(f"x_{i}_{j}")

    # Route flow.
    solver.Add(
        solver.Sum(x[(START_NODE, j)] for j in data.poi_ids + [END_NODE]) == 1
    )
    solver.Add(
        solver.Sum(x[(i, END_NODE)] for i in [START_NODE] + data.poi_ids) == 1
    )
    for poi_id in data.poi_ids:
        outgoing = [x[(poi_id, j)] for j in data.all_node_ids if (poi_id, j) in x]
        incoming = [x[(j, poi_id)] for j in data.all_node_ids if (j, poi_id) in x]
        solver.Add(solver.Sum(outgoing) == y[poi_id])
        solver.Add(solver.Sum(incoming) == y[poi_id])

    # Time propagation.
    for (i, j), arc_var in x.items():
        depart_expr = inp.departure_start_min if i == START_NODE else a[i] + s[i]
        arrival_var = a_end if j == END_NODE else a[j]
        solver.Add(
            arrival_var
            >= depart_expr + data.travel[(i, j)] - big_m * (1 - arc_var)
        )

    solver.Add(a_end <= inp.return_deadline_min)
    solver.Add(a_end >= inp.departure_start_min)

    # POI constraints.
    for poi_id in data.poi_ids:
        open_min, close_min = data.open_window[poi_id]
        stay_min, stay_max = data.stay_bounds[poi_id]
        meal_start, meal_end = data.meal_window[poi_id]
        solver.Add(s[poi_id] >= stay_min * y[poi_id])
        solver.Add(s[poi_id] <= stay_max * y[poi_id])
        solver.Add(a[poi_id] >= open_min * y[poi_id])
        solver.Add(a[poi_id] <= upper_bound * y[poi_id])
        solver.Add(a[poi_id] + s[poi_id] <= close_min + big_m * (1 - y[poi_id]))
        if meal_start is not None and meal_end is not None:
            solver.Add(a[poi_id] >= meal_start * y[poi_id])
            solver.Add(a[poi_id] <= meal_end + big_m * (1 - y[poi_id]))
        last_adm = data.last_admission[poi_id]
        if last_adm is not None:
            solver.Add(a[poi_id] <= last_adm + big_m * (1 - y[poi_id]))

    groups = _category_groups(data)
    cafe_ids = _cafe_ids(data)

    for category_name, _reason_code in MEAL_REASON_CODES:
        category_ids = groups[category_name]
        if _is_category_required(inp, category_name) and category_ids:
            solver.Add(solver.Sum(y[poi_id] for poi_id in category_ids) == 1)
    if _is_category_required(inp, "sunset") and groups["sunset"]:
        if inp.weather_mode == "rain":
            solver.Add(solver.Sum(y[poi_id] for poi_id in groups["sunset"]) <= 1)
        else:
            solver.Add(solver.Sum(y[poi_id] for poi_id in groups["sunset"]) == 1)
    if _requires_additional_cafe(inp) and cafe_ids:
        solver.Add(solver.Sum(y[poi_id] for poi_id in cafe_ids) >= 1)

    for poi_id in inp.must_visit:
        if poi_id in y:
            solver.Add(y[poi_id] == 1)
    for poi_id in inp.excluded_poi_ids:
        if poi_id in y:
            solver.Add(y[poi_id] == 0)

    for if_visit_poi_id, require_poi_id in data.dependencies:
        if if_visit_poi_id not in y:
            continue
        if require_poi_id in y:
            solver.Add(y[if_visit_poi_id] <= y[require_poi_id])
        else:
            solver.Add(y[if_visit_poi_id] == 0)

    objective = solver.Objective()
    for poi_id in data.poi_ids:
        objective.SetCoefficient(y[poi_id], _visit_base_score(poi_id, inp, data))

        meal_start, meal_end = data.meal_window[poi_id]
        if meal_start is not None and meal_end is not None:
            meal_late = solver.NumVar(0.0, float(upper_bound), f"meal_late_{poi_id}")
            solver.Add(meal_late >= a[poi_id] - meal_start)
            solver.Add(meal_late <= big_m * y[poi_id])
            objective.SetCoefficient(meal_late, -LATE_MEAL_PENALTY)

            if _has_wait_risk(data, poi_id):
                wait_risk = solver.NumVar(
                    0.0, float(upper_bound), f"wait_risk_tight_{poi_id}"
                )
                risk_start = _wait_risk_start(meal_start, meal_end)
                solver.Add(wait_risk >= a[poi_id] - risk_start)
                solver.Add(wait_risk <= big_m * y[poi_id])
                objective.SetCoefficient(wait_risk, -WAIT_RISK_PENALTY)

    for (i, j), arc_var in x.items():
        objective.SetCoefficient(arc_var, -_travel_penalty(data.travel[(i, j)], inp))

    objective.SetMaximization()
    status = solver.Solve()

    if status not in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
        reasons = _diagnose_infeasibility(inp, data)
        if backend == "CBC" and status == pywraplp.Solver.NOT_SOLVED:
            reasons.append("cbc_timeout")
        return status, _infeasible_result(reasons)

    ordered_poi_ids: list[int] = []
    arrival_minutes: list[int | None] = []
    departure_minutes: list[int | None] = []
    leg_minutes: list[int | None] = []
    current = START_NODE
    visited: set[int] = set()
    while current != END_NODE:
        next_nodes = [
            j
            for (i, j), arc_var in x.items()
            if i == current and arc_var.solution_value() > 0.5
        ]
        if not next_nodes:
            break
        nxt = next_nodes[0]
        leg_minutes.append(data.travel[(current, nxt)])
        if nxt == END_NODE:
            end_arrival = int(round(a_end.solution_value()))
            arrival_minutes.append(end_arrival)
            departure_minutes.append(end_arrival)
            current = END_NODE
            continue
        if nxt in visited:
            break
        visited.add(nxt)
        ordered_poi_ids.append(nxt)
        arrival = int(round(a[nxt].solution_value()))
        stay = int(round(s[nxt].solution_value()))
        arrival_minutes.append(arrival)
        departure_minutes.append(arrival + stay)
        current = nxt

    return status, SolverResult(
        feasible=True,
        objective=objective.Value(),
        ordered_poi_ids=ordered_poi_ids,
        arrival_minutes=arrival_minutes,
        departure_minutes=departure_minutes,
        leg_minutes=leg_minutes,
        reason_codes=[],
        solve_ms=0,
    )


def _heuristic_order_for_subset(
    subset_ids: list[int], data: PreparedSolverData
) -> list[int]:
    return sorted(
        subset_ids,
        key=lambda poi_id: (
            CATEGORY_RANK.get(data.category.get(poi_id, ""), 55),
            data.open_window[poi_id][1],
        ),
    )


def _simulate_subset(
    subset_ids: list[int], inp: SolverInput, data: PreparedSolverData
) -> tuple[bool, float, list[int], list[int], list[int]]:
    if inp.must_have_cafe and not any(
        _has_cafe_tag(data.tags.get(poi_id, set())) for poi_id in subset_ids
    ):
        return False, 0.0, [], [], []

    current = START_NODE
    now = inp.departure_start_min
    arrivals: list[int] = []
    departures: list[int] = []
    legs: list[int] = []
    score = 0.0

    for poi_id in subset_ids:
        leg = data.travel[(current, poi_id)]
        arrival = now + leg
        open_min, close_min = data.open_window[poi_id]
        stay_min, _stay_max = data.stay_bounds[poi_id]
        meal_start, meal_end = data.meal_window[poi_id]
        if meal_start is not None and meal_end is not None:
            arrival = max(arrival, meal_start)
            if arrival > meal_end:
                return False, 0.0, [], [], []
        else:
            arrival = max(arrival, open_min)
        last_adm = data.last_admission[poi_id]
        if last_adm is not None and arrival > last_adm:
            return False, 0.0, [], [], []
        if arrival + stay_min > close_min:
            return False, 0.0, [], [], []
        depart = arrival + stay_min
        arrivals.append(arrival)
        departures.append(depart)
        legs.append(leg)
        score += _visit_base_score(poi_id, inp, data)
        if meal_start is not None and meal_end is not None:
            score -= LATE_MEAL_PENALTY * max(0, arrival - meal_start)
            if _has_wait_risk(data, poi_id):
                risk_start = _wait_risk_start(meal_start, meal_end)
                score -= WAIT_RISK_PENALTY * max(0, arrival - risk_start)
        score -= _travel_penalty(leg, inp)
        now = depart
        current = poi_id

    end_leg = data.travel[(current, END_NODE)]
    end_arrival = now + end_leg
    if end_arrival > inp.return_deadline_min:
        return False, 0.0, [], [], []
    arrivals.append(end_arrival)
    departures.append(end_arrival)
    legs.append(end_leg)
    score -= _travel_penalty(end_leg, inp)
    return True, score, arrivals, departures, legs


def _solve_with_heuristic(inp: SolverInput, data: PreparedSolverData) -> SolverResult:
    groups = _category_groups(data)
    cafe_ids = _cafe_ids(data)
    missing_codes = _precheck_reason_codes(inp, data)
    if missing_codes:
        return _infeasible_result(_dedupe_codes(data.reasons, missing_codes))

    category_choices = {
        category_name: (
            groups[category_name] if _is_category_required(inp, category_name) else [None]
        )
        for category_name, _reason_code in MEAL_REASON_CODES
    }
    sunset_choices: list[int | None] = (
        groups["sunset"] if _is_category_required(inp, "sunset") and groups["sunset"] else [None]
    )
    best: tuple[float, list[int], list[int], list[int], list[int]] | None = None

    for lunch_id, dinner_id, sweets_id, sunset_id in itertools.product(
        category_choices["lunch"],
        category_choices["dinner"],
        category_choices["sweets"],
        sunset_choices,
    ):
        chosen = {
            poi_id
            for poi_id in (*inp.must_visit, lunch_id, dinner_id, sweets_id, sunset_id)
            if poi_id is not None
        }
        cafe_choices: list[int | None] = [None]
        if _requires_additional_cafe(inp) and not any(
            _has_cafe_tag(data.tags.get(poi_id, set())) for poi_id in chosen
        ):
            cafe_choices = cafe_ids

        for cafe_id in cafe_choices:
            chosen_with_cafe = chosen | ({cafe_id} if cafe_id is not None else set())
            optional = sorted(
                (
                    poi_id
                    for poi_id in data.poi_ids
                    if poi_id not in chosen_with_cafe
                    and data.category.get(poi_id) not in OPTIONAL_CATEGORY_SET
                ),
                key=lambda poi_id: data.utility[poi_id],
                reverse=True,
            )[:2]
            seen_subsets: set[tuple[int, ...]] = set()
            for subset_option in (
                sorted(chosen_with_cafe),
                sorted(chosen_with_cafe | set(optional[:1])),
                sorted(chosen_with_cafe | set(optional[:2])),
            ):
                expanded_subset = _expand_dependency_closure(
                    set(subset_option),
                    data.dependencies,
                    available_ids=set(data.poi_ids),
                )
                if expanded_subset is None:
                    continue
                subset_key = tuple(sorted(expanded_subset))
                if subset_key in seen_subsets:
                    continue
                seen_subsets.add(subset_key)
                subset_ids = _heuristic_order_for_subset(list(subset_key), data)
                ok, score, arrivals, departures, legs = _simulate_subset(subset_ids, inp, data)
                if ok and (best is None or score > best[0]):
                    best = (score, subset_ids, arrivals, departures, legs)

    if best is None:
        return _infeasible_result(_diagnose_infeasibility(inp, data))

    score, ordered_ids, arrivals, departures, legs = best
    return SolverResult(
        feasible=True,
        objective=score,
        ordered_poi_ids=ordered_ids,
        arrival_minutes=arrivals,
        departure_minutes=departures,
        leg_minutes=legs,
        reason_codes=["heuristic_fallback"],
        solve_ms=0,
    )


def solve_trip(session: Session, inp: SolverInput) -> SolverResult:
    started = time.perf_counter()
    data = _prepare_solver_data(session, inp)

    precheck_codes = _precheck_reason_codes(inp, data)
    if precheck_codes:
        result = _infeasible_result(_dedupe_codes(data.reasons, precheck_codes))
        result.solve_ms = int((time.perf_counter() - started) * 1000)
        return result

    if len(data.poi_ids) > MAX_HEURISTIC_NODES:
        result = _solve_with_heuristic(inp, data)
        if result.feasible:
            result = _normalize_departure_window(inp, data, result)
        result.solve_ms = int((time.perf_counter() - started) * 1000)
        return result

    status, result = _solve_with_mip(inp, data)
    if status in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
        result = _normalize_departure_window(inp, data, result)
        result.solve_ms = int((time.perf_counter() - started) * 1000)
        return result
    if status in (pywraplp.Solver.NOT_SOLVED, pywraplp.Solver.ABNORMAL):
        fallback = _solve_with_heuristic(inp, data)
        fallback.reason_codes = _dedupe_codes(result.reason_codes, fallback.reason_codes)
        if fallback.feasible:
            fallback = _normalize_departure_window(inp, data, fallback)
        fallback.solve_ms = int((time.perf_counter() - started) * 1000)
        return fallback

    result.solve_ms = int((time.perf_counter() - started) * 1000)
    return result
