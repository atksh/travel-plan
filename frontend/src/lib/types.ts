export type PoiSummary = {
  id: number;
  name: string;
  lat: number;
  lng: number;
  google_place_id: string | null;
  primary_category: string;
  is_active: boolean;
};

export type CandidateOut = {
  id: number;
  poi_id: number;
  poi_name: string;
  primary_category: string;
  status: string;
  source: string;
  must_visit: boolean;
  excluded: boolean;
  locked_in: boolean;
  locked_out: boolean;
  user_note: string | null;
  utility_override: number | null;
  candidate_rank: number | null;
};

export type TripPreferenceOut = {
  driving_penalty_weight: number;
  max_continuous_drive_minutes: number;
  preferred_lunch_tags: string[];
  preferred_dinner_tags: string[];
  must_have_cafe: boolean;
  budget_band: string | null;
  pace_style: string;
};

export type PlannedStopOut = {
  id?: number | null;
  sequence_order: number;
  poi_id: number | null;
  poi_name: string;
  label: string;
  node_kind: string;
  lat: number;
  lng: number;
  arrival_min: number;
  departure_min: number;
  stay_min: number;
  leg_from_prev_min: number | null;
  leg_polyline?: string | null;
  status: string;
};

export type RouteLegOut = {
  from_sequence_order: number;
  to_sequence_order: number;
  duration_minutes: number;
  distance_meters: number | null;
  encoded_polyline: string;
};

export type SolverRunOut = {
  id: number;
  objective_value: number | null;
  infeasible_reason: string | null;
  solve_ms: number;
};

export type SolveSnapshotOut = {
  feasible: boolean;
  objective: number | null;
  ordered_poi_ids: number[];
  reason_codes: string[];
  solve_ms: number;
  solver_run_id: number | null;
  used_bucket: string;
  used_traffic_matrix: boolean;
  shortlist_ids: number[];
  planned_stops: PlannedStopOut[];
  route_legs: RouteLegOut[];
};

export type TripDetailOut = {
  id: number;
  state: string;
  plan_date: string;
  origin_lat: number;
  origin_lng: number;
  origin_label: string;
  dest_lat: number;
  dest_lng: number;
  dest_label: string;
  departure_window_start_min: number;
  departure_window_end_min: number;
  return_deadline_min: number;
  weather_mode: string;
  preference_profile: TripPreferenceOut | null;
  candidates: CandidateOut[];
  latest_solve: SolveSnapshotOut | null;
};

export type SolveResponse = SolveSnapshotOut & {
  alternatives: CandidateOut[];
};

export type RoutePreviewOut = {
  solve: SolveSnapshotOut | null;
};

export type EventOut = {
  id: number;
  event_type: string;
  payload_json: Record<string, unknown> | null;
  recorded_at: string;
};

export type ActiveTripStateOut = {
  completed_poi_ids: number[];
  in_progress_poi_id: number | null;
  current_stop: PlannedStopOut | null;
  next_stop: PlannedStopOut | null;
};

export type ActiveTripBootstrapOut = {
  trip: TripDetailOut;
  events: EventOut[];
  pois: PoiSummary[];
  active_state: ActiveTripStateOut;
};
