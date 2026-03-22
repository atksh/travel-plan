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
  poi_name: string | null;
  label?: string | null;
  node_kind: string;
  lat?: number | null;
  lng?: number | null;
  arrival_min: number | null;
  departure_min: number | null;
  stay_min: number | null;
  leg_from_prev_min: number | null;
  status: string;
};

export type SolverRunOut = {
  id: number;
  objective_value: number | null;
  infeasible_reason: string | null;
  solve_ms: number;
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
  latest_route: PlannedStopOut[];
  latest_solver_run: SolverRunOut | null;
};

export type SolveResponse = {
  feasible: boolean;
  objective: number | null;
  ordered_poi_ids: number[];
  reason_codes: string[];
  solve_ms: number;
  planned_stops: PlannedStopOut[];
  solver_run_id: number | null;
  alternatives: CandidateOut[];
};

export type RoutePreviewOut = {
  stops: PlannedStopOut[];
};

export type EventOut = {
  id: number;
  event_type: string;
  payload_json: Record<string, unknown> | null;
  recorded_at: string;
};
