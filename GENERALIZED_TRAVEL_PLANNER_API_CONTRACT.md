# Generalized Travel Planner API Contract

Status: Draft  
Audience: Backend, frontend, QA  
Scope: Target-state HTTP contract for the generalized single-day planner  
Related docs:

- [GENERALIZED_TRAVEL_PLANNER_SPEC.md](GENERALIZED_TRAVEL_PLANNER_SPEC.md)
- [GENERALIZED_TRAVEL_PLANNER_BACKEND_RFC.md](GENERALIZED_TRAVEL_PLANNER_BACKEND_RFC.md)
- [GENERALIZED_TRAVEL_PLANNER_FRONTEND_UX_SPEC.md](GENERALIZED_TRAVEL_PLANNER_FRONTEND_UX_SPEC.md)

Current contract anchors:

- [backend/app/schemas/trip.py](backend/app/schemas/trip.py)
- [backend/app/schemas/poi.py](backend/app/schemas/poi.py)
- [backend/app/api/routes/trips.py](backend/app/api/routes/trips.py)
- [backend/app/api/routes/pois.py](backend/app/api/routes/pois.py)
- [frontend/src/lib/types.ts](frontend/src/lib/types.ts)

## 1. Purpose

This document defines the target-state API contract for the generalized travel planner. It is the normative contract reference for:

- resource names
- request and response shapes
- preview vs accepted solve semantics
- execution and replan flows

This contract is intentionally a breaking evolution from the current `/api/pois`, `/api/trips/{id}/route-preview`, and `/api/trips/{id}/active-bootstrap` model.

## 2. Contract Principles

- Backend is the canonical source of truth.
- All core planning and execution flows must use explicit typed payloads.
- The API must fail explicitly on invalid state or missing required data.
- Preview must not silently degrade to estimated or partial core timing.
- Historical accepted runs and execution history must remain readable.

## 3. Common Conventions

### 3.1 IDs

All persisted resources use stable numeric ids in v1:

- `place_id`
- `trip_id`
- `candidate_id`
- `rule_id`
- `solve_run_id`
- `execution_session_id`
- `event_id`

Ephemeral preview resources use opaque string ids:

- `preview_id`

### 3.2 Time Representation

Single-day planning uses integer minutes from local midnight:

- `departure_window_start_min`
- `departure_window_end_min`
- `end_constraint_minute_of_day`
- stop arrival/departure/stay fields

Absolute timestamps use RFC3339 strings:

- `created_at`
- `updated_at`
- `recorded_at`
- `started_at`
- `completed_at`

### 3.3 Error Shape

The error envelope remains contract-first and explicit:

```json
{
  "error": {
    "code": "RULE_VALIDATION_FAILED",
    "message": "Rule parameters are invalid for rule_kind=arrival_window.",
    "details": {
      "rule_kind": "arrival_window",
      "field": "parameters.arrive_before_min"
    }
  }
}
```

### 3.4 Versioning And Promotion Safety

Workspace-mutating or preview-promotion calls may require:

- `workspace_version`
- `preview_id`

If the workspace changes after a preview is generated, preview promotion must fail with a stable conflict error.

## 4. Shared Resource Shapes

### 4.1 PlaceSummary

```json
{
  "id": 123,
  "name": "Seaside Cafe",
  "lat": 35.0,
  "lng": 139.8,
  "source": "google_places",
  "archived": false,
  "category": "cafe",
  "tags": ["scenic", "cafe"],
  "traits": ["indoor", "parking_available"]
}
```

### 4.2 PlaceDetail

```json
{
  "id": 123,
  "name": "Seaside Cafe",
  "lat": 35.0,
  "lng": 139.8,
  "source": "google_places",
  "archived": false,
  "category": "cafe",
  "tags": ["scenic", "cafe"],
  "traits": ["indoor", "parking_available"],
  "visit_profile": {
    "stay_min_minutes": 30,
    "stay_preferred_minutes": 45,
    "stay_max_minutes": 90,
    "price_band": "moderate",
    "rating": 4.4,
    "is_indoor": true
  },
  "availability_rules": [],
  "source_records": [],
  "notes": null
}
```

### 4.3 TripSummary

```json
{
  "id": 55,
  "title": "Sunday coast drive",
  "plan_date": "2026-04-05",
  "state": "working",
  "timezone": "Asia/Tokyo"
}
```

### 4.4 TripDetail

```json
{
  "id": 55,
  "title": "Sunday coast drive",
  "plan_date": "2026-04-05",
  "state": "working",
  "timezone": "Asia/Tokyo",
  "origin": {
    "label": "Home",
    "lat": 35.72,
    "lng": 139.79
  },
  "destination": {
    "label": "Hotel",
    "lat": 35.45,
    "lng": 139.92
  },
  "departure_window_start_min": 480,
  "departure_window_end_min": 540,
  "end_constraint": {
    "kind": "arrive_by",
    "minute_of_day": 1260
  },
  "context": {
    "weather": null,
    "traffic_profile": "default"
  }
}
```

### 4.5 Candidate

```json
{
  "id": 901,
  "place_id": 123,
  "candidate_state": "active",
  "priority": "high",
  "locked_in": false,
  "locked_out": false,
  "utility_override": null,
  "stay_override": {
    "min": null,
    "preferred": null,
    "max": null
  },
  "time_preference": {
    "arrive_after_min": null,
    "arrive_before_min": null,
    "depart_after_min": null,
    "depart_before_min": null
  },
  "manual_order_hint": null,
  "user_note": null,
  "place": {
    "id": 123,
    "name": "Seaside Cafe",
    "lat": 35.0,
    "lng": 139.8,
    "source": "google_places",
    "archived": false,
    "category": "cafe",
    "tags": ["scenic", "cafe"],
    "traits": ["indoor"]
  }
}
```

### 4.6 Rule

```json
{
  "id": 301,
  "trip_id": 55,
  "rule_kind": "selection_count",
  "scope": "trip",
  "mode": "hard",
  "weight": null,
  "target": {
    "kind": "tag",
    "value": "scenic"
  },
  "operator": "include",
  "parameters": {
    "min_count": 1,
    "max_count": 2
  },
  "carry_forward_strategy": "mark_satisfied",
  "label": "Include scenic stops",
  "description": "At least one scenic stop",
  "created_by_surface": "ui"
}
```

### 4.7 SolveStop

```json
{
  "sequence_order": 1,
  "node_kind": "place",
  "place_id": 123,
  "label": "Seaside Cafe",
  "lat": 35.0,
  "lng": 139.8,
  "arrival_min": 600,
  "departure_min": 645,
  "stay_min": 45,
  "leg_from_prev_min": 15,
  "status": "planned"
}
```

### 4.8 RouteLeg

```json
{
  "from_sequence_order": 0,
  "to_sequence_order": 1,
  "duration_minutes": 15,
  "distance_meters": 12000,
  "encoded_polyline": "..."
}
```

### 4.9 RuleResult

```json
{
  "rule_id": 301,
  "status": "satisfied",
  "score_impact": 0,
  "explanation": "One scenic place was selected."
}
```

### 4.10 CandidateDiagnostic

```json
{
  "candidate_id": 901,
  "status": "unselected",
  "explanation": "Dropped due to time pressure after arrival window constraints.",
  "blocking_rule_ids": [402]
}
```

### 4.11 SolveSummary

```json
{
  "feasible": true,
  "score": 42.7,
  "total_drive_minutes": 180,
  "total_stay_minutes": 240,
  "total_distance_meters": 142000,
  "start_time_min": 495,
  "end_time_min": 1230
}
```

### 4.12 SolvePayload

```json
{
  "summary": {
    "feasible": true,
    "score": 42.7,
    "total_drive_minutes": 180,
    "total_stay_minutes": 240,
    "total_distance_meters": 142000,
    "start_time_min": 495,
    "end_time_min": 1230
  },
  "stops": [],
  "route_legs": [],
  "selected_place_ids": [123, 456],
  "unselected_candidates": [],
  "rule_results": [],
  "warnings": [],
  "alternatives": []
}
```

## 5. Place Catalog API

### `GET /api/places`

Purpose:

- list local place catalog results

Query params:

- `q`
- `bounds`
- `radius_m`
- `tags`
- `traits`
- `source`
- `archived`
- `limit`
- `cursor`

Response:

```json
{
  "items": [],
  "next_cursor": null
}
```

### `POST /api/places/search-text`

Purpose:

- search external provider results without persisting

Request:

```json
{
  "query": "ocean cafe",
  "region": "jp"
}
```

Response:

```json
{
  "results": []
}
```

### `POST /api/places/search-area`

Purpose:

- search provider results by viewport or radius

Request:

```json
{
  "center": { "lat": 35.0, "lng": 139.8 },
  "radius_m": 8000
}
```

### `POST /api/places/import`

Purpose:

- import one provider place into local catalog

Request:

```json
{
  "provider": "google_places",
  "provider_place_id": "abc123",
  "overrides": {
    "name": "My label",
    "category": "cafe",
    "tags": ["scenic"],
    "traits": ["indoor"]
  }
}
```

Response:

- `201 Created`
- body: `PlaceDetail`

### `POST /api/places`

Purpose:

- create a manual place

Request:

```json
{
  "name": "Private parking lot",
  "lat": 35.1,
  "lng": 139.9,
  "tags": ["parking"],
  "traits": ["parking_available"],
  "visit_profile": {
    "stay_min_minutes": 5,
    "stay_preferred_minutes": 5,
    "stay_max_minutes": 10
  }
}
```

Response:

- `201 Created`
- body: `PlaceDetail`

### `GET /api/places/{placeId}`

Response:

- `200 OK`
- body: `PlaceDetail`

### `PATCH /api/places/{placeId}`

Response:

- `200 OK`
- body: `PlaceDetail`

### `DELETE /api/places/{placeId}`

Behavior:

- soft archive when referenced by historical records
- hard delete only if safe

Response:

```json
{
  "ok": true
}
```

## 6. Trip Workspace API

### `POST /api/trips`

Purpose:

- create trip frame only

Request:

```json
{
  "title": "Sunday coast drive",
  "plan_date": "2026-04-05",
  "origin": {
    "label": "Home",
    "lat": 35.72,
    "lng": 139.79
  },
  "destination": {
    "label": "Hotel",
    "lat": 35.45,
    "lng": 139.92
  },
  "departure_window_start_min": 480,
  "departure_window_end_min": 540,
  "end_constraint": {
    "kind": "arrive_by",
    "minute_of_day": 1260
  },
  "timezone": "Asia/Tokyo"
}
```

Response:

- `201 Created`
- body: `TripDetail`

### `GET /api/trips/{tripId}`

Response:

```json
{
  "trip": {},
  "workspace_version": 7,
  "candidates": [],
  "rules": [],
  "latest_accepted_run": null,
  "planning_summary": null
}
```

### `PATCH /api/trips/{tripId}`

Purpose:

- update trip frame metadata and allowed state changes

### `GET /api/trips/{tripId}/candidates`

Response:

```json
{
  "items": []
}
```

### `POST /api/trips/{tripId}/candidates`

Request:

```json
{
  "place_id": 123,
  "priority": "high"
}
```

Response:

- `201 Created`
- body: `Candidate`

### `PATCH /api/trips/{tripId}/candidates/{candidateId}`

Request may update:

- candidate state
- priority
- lock flags
- utility override
- stay override
- time preference
- manual order hint
- note

### `DELETE /api/trips/{tripId}/candidates/{candidateId}`

Response:

```json
{
  "ok": true
}
```

### `GET /api/trips/{tripId}/rules`

Response:

```json
{
  "items": []
}
```

### `POST /api/trips/{tripId}/rules`

Request:

```json
{
  "rule_kind": "selection_count",
  "scope": "trip",
  "mode": "hard",
  "target": {
    "kind": "tag",
    "value": "scenic"
  },
  "operator": "include",
  "parameters": {
    "min_count": 1,
    "max_count": 2
  },
  "carry_forward_strategy": "mark_satisfied",
  "label": "Include scenic stops"
}
```

Response:

- `201 Created`
- body: `Rule`

### `PATCH /api/trips/{tripId}/rules/{ruleId}`

Response:

- `200 OK`
- body: `Rule`

### `DELETE /api/trips/{tripId}/rules/{ruleId}`

Response:

```json
{
  "ok": true
}
```

## 7. Preview And Solve API

### `POST /api/trips/{tripId}/preview`

Purpose:

- create a non-persistent preview from canonical workspace plus optional draft overrides

Request:

```json
{
  "workspace_version": 7,
  "draft_candidate_patches": [],
  "draft_rule_patches": [],
  "draft_order_edits": []
}
```

Response:

```json
{
  "preview_id": "pvw_123",
  "workspace_version": 7,
  "based_on_run_id": 44,
  "solve": {
    "summary": {
      "feasible": true,
      "score": 42.7,
      "total_drive_minutes": 180,
      "total_stay_minutes": 240,
      "total_distance_meters": 142000,
      "start_time_min": 495,
      "end_time_min": 1230
    },
    "stops": [],
    "route_legs": [],
    "selected_place_ids": [123],
    "unselected_candidates": [],
    "rule_results": [],
    "warnings": [],
    "alternatives": []
  }
}
```

### `POST /api/trips/{tripId}/solve`

Purpose:

- persist accepted solve

Request form A: solve current workspace

```json
{
  "workspace_version": 7
}
```

Request form B: promote preview

```json
{
  "preview_id": "pvw_123",
  "workspace_version": 7
}
```

Response:

```json
{
  "solve_run_id": 45,
  "accepted": true,
  "solve": {
    "summary": {
      "feasible": true,
      "score": 42.7,
      "total_drive_minutes": 180,
      "total_stay_minutes": 240,
      "total_distance_meters": 142000,
      "start_time_min": 495,
      "end_time_min": 1230
    },
    "stops": [],
    "route_legs": [],
    "selected_place_ids": [123],
    "unselected_candidates": [],
    "rule_results": [],
    "warnings": [],
    "alternatives": []
  }
}
```

### `GET /api/trips/{tripId}/solve-runs`

Response:

```json
{
  "items": [
    {
      "solve_run_id": 45,
      "run_kind": "planned",
      "accepted_at": "2026-04-05T02:00:00Z",
      "summary": {
        "feasible": true,
        "score": 42.7,
        "total_drive_minutes": 180,
        "total_stay_minutes": 240,
        "total_distance_meters": 142000,
        "start_time_min": 495,
        "end_time_min": 1230
      }
    }
  ]
}
```

### `GET /api/trips/{tripId}/solve-runs/{runId}`

Response:

- `200 OK`
- body: full accepted solve payload

## 8. Execution API

### `POST /api/trips/{tripId}/execution/start`

Response:

```json
{
  "execution_session_id": 90,
  "trip_state": "active",
  "active_run_id": 45
}
```

### `GET /api/trips/{tripId}/execution/bootstrap`

Response:

```json
{
  "trip": {},
  "execution_session": {
    "execution_session_id": 90,
    "active_run_id": 45,
    "status": "active",
    "started_at": "2026-04-05T02:30:00Z",
    "current_stop_id": null
  },
  "active_solve": {
    "summary": {
      "feasible": true,
      "score": 42.7,
      "total_drive_minutes": 180,
      "total_stay_minutes": 240,
      "total_distance_meters": 142000,
      "start_time_min": 495,
      "end_time_min": 1230
    },
    "stops": [],
    "route_legs": [],
    "selected_place_ids": [123],
    "unselected_candidates": [],
    "rule_results": [],
    "warnings": [],
    "alternatives": []
  },
  "events": [],
  "current_stop": null,
  "next_stop": null,
  "replan_readiness": {
    "can_replan": true,
    "reasons": []
  }
}
```

### `POST /api/trips/{tripId}/execution/events`

Request:

```json
{
  "event_type": "arrived",
  "payload": {
    "place_id": 123
  }
}
```

Response:

```json
{
  "event_id": 501,
  "event_type": "arrived",
  "payload": {
    "place_id": 123
  },
  "recorded_at": "2026-04-05T04:12:00Z"
}
```

### `POST /api/trips/{tripId}/execution/replan-preview`

Request:

```json
{
  "workspace_version": 9,
  "current_context": {
    "current_lat": 35.1,
    "current_lng": 139.9
  },
  "draft_candidate_patches": [],
  "draft_rule_patches": []
}
```

Response:

```json
{
  "preview_id": "rpvw_123",
  "workspace_version": 9,
  "solve": {
    "summary": {
      "feasible": true,
      "score": 38.2,
      "total_drive_minutes": 110,
      "total_stay_minutes": 150,
      "total_distance_meters": 78000,
      "start_time_min": 900,
      "end_time_min": 1220
    },
    "stops": [],
    "route_legs": [],
    "selected_place_ids": [456],
    "unselected_candidates": [],
    "rule_results": [],
    "warnings": ["One soft rule was violated."],
    "alternatives": []
  }
}
```

### `POST /api/trips/{tripId}/execution/replan`

Request:

```json
{
  "preview_id": "rpvw_123",
  "workspace_version": 9
}
```

Response:

```json
{
  "execution_session_id": 90,
  "active_run_id": 46,
  "accepted": true,
  "solve": {
    "summary": {
      "feasible": true,
      "score": 38.2,
      "total_drive_minutes": 110,
      "total_stay_minutes": 150,
      "total_distance_meters": 78000,
      "start_time_min": 900,
      "end_time_min": 1220
    },
    "stops": [],
    "route_legs": [],
    "selected_place_ids": [456],
    "unselected_candidates": [],
    "rule_results": [],
    "warnings": [],
    "alternatives": []
  }
}
```

## 9. Error Cases

Required stable error scenarios:

- `PLACE_IMPORT_UNSUPPORTED`
- `PLACE_NOT_FOUND`
- `TRIP_NOT_FOUND`
- `CANDIDATE_NOT_FOUND`
- `RULE_VALIDATION_FAILED`
- `WORKSPACE_VERSION_MISMATCH`
- `PREVIEW_NOT_FOUND`
- `PREVIEW_EXPIRED`
- `SOLVE_INFEASIBLE`
- `EXECUTION_NOT_STARTED`
- `REPLAN_NOT_ALLOWED`
- `ROUTING_DATA_INCOMPLETE`

## 10. Contract-Level Compatibility Notes

Relative to the current codebase:

- `places` replaces `pois`
- `preview` replaces the current limited `route-preview`
- `execution/bootstrap` replaces the current `active-bootstrap`
- `TripPreferenceOut` is no longer the main way to express intent
- structured `rule_results` and `candidate diagnostics` replace simple `reason_codes`

## 11. Validation Requirements

The contract is acceptable when:

- every target resource has a stable request/response shape
- preview and solve are distinguishable in the contract
- execution bootstrap is self-sufficient for the frontend
- rule validation failures are explicit and typed
- version mismatch behavior is explicit

