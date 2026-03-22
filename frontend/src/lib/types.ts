export type PlaceSummary = {
  id: number;
  name: string;
  lat: number;
  lng: number;
  source: string;
  archived: boolean;
  category: string | null;
  tags: string[];
  traits: string[];
};

export type PlaceDetail = PlaceSummary & {
  visit_profile: {
    stay_min_minutes: number;
    stay_preferred_minutes: number;
    stay_max_minutes: number;
    price_band: string | null;
    rating: number | null;
    accessibility_notes: string | null;
  } | null;
  availability_rules: Array<{
    weekday: number | null;
    open_minute: number;
    close_minute: number;
    valid_from: string | null;
    valid_to: string | null;
    last_admission_minute: number | null;
    closed_flag: boolean;
  }>;
  source_records: Array<{
    provider: string;
    provider_place_id: string | null;
    source_url: string | null;
    fetched_at: string;
    parser_version: string;
  }>;
  notes: string | null;
};

export type PlaceSearchResult = {
  provider: string;
  provider_place_id: string;
  name: string;
  lat: number;
  lng: number;
  primary_type: string | null;
  rating: number | null;
  price_level: string | null;
};

export type TripSummary = {
  id: number;
  title: string;
  plan_date: string;
  state: string;
  timezone: string;
};

export type TripDetail = TripSummary & {
  origin: {
    label: string;
    lat: number;
    lng: number;
  };
  destination: {
    label: string;
    lat: number;
    lng: number;
  };
  departure_window_start_min: number;
  departure_window_end_min: number;
  end_constraint: {
    kind: string;
    minute_of_day: number;
  };
  context: {
    weather: string | null;
    traffic_profile: string;
  };
};

export type Candidate = {
  id: number;
  place_id: number;
  candidate_state: string;
  priority: string;
  locked_in: boolean;
  locked_out: boolean;
  utility_override: number | null;
  stay_override: {
    min: number | null;
    preferred: number | null;
    max: number | null;
  };
  time_preference: {
    arrive_after_min: number | null;
    arrive_before_min: number | null;
    depart_after_min: number | null;
    depart_before_min: number | null;
  };
  manual_order_hint: number | null;
  user_note: string | null;
  place: PlaceSummary;
};

export type TripRule = {
  id: number;
  trip_id: number;
  rule_kind: string;
  scope: string;
  mode: string;
  weight: number | null;
  target: {
    kind: string;
    value: string | number | null;
    data: Record<string, unknown>;
  };
  operator: string;
  parameters: Record<string, unknown>;
  carry_forward_strategy: string;
  label: string;
  description: string | null;
  created_by_surface: string;
};

export type SolveSummary = {
  feasible: boolean;
  score: number | null;
  total_drive_minutes: number;
  total_stay_minutes: number;
  total_distance_meters: number;
  start_time_min: number;
  end_time_min: number;
};

export type SolveStop = {
  sequence_order: number;
  node_kind: string;
  place_id: number | null;
  label: string;
  lat: number;
  lng: number;
  arrival_min: number;
  departure_min: number;
  stay_min: number;
  leg_from_prev_min: number | null;
  status: string;
};

export type RouteLeg = {
  from_sequence_order: number;
  to_sequence_order: number;
  duration_minutes: number;
  distance_meters: number | null;
  encoded_polyline: string;
};

export type RuleResult = {
  rule_id: number;
  status: string;
  score_impact: number;
  explanation: string;
};

export type CandidateDiagnostic = {
  candidate_id: number;
  status: string;
  explanation: string;
  blocking_rule_ids: number[];
};

export type SolveAlternative = {
  label: string;
  description: string;
  candidate_id: number | null;
  place_id: number | null;
};

export type SolvePayload = {
  summary: SolveSummary;
  stops: SolveStop[];
  route_legs: RouteLeg[];
  selected_place_ids: number[];
  unselected_candidates: CandidateDiagnostic[];
  rule_results: RuleResult[];
  warnings: string[];
  alternatives: SolveAlternative[];
};

export type PreviewResponse = {
  preview_id: string;
  workspace_version: number;
  based_on_run_id: number | null;
  solve: SolvePayload;
};

export type SolveAcceptedResponse = {
  solve_run_id: number;
  accepted: boolean;
  solve: SolvePayload;
};

export type SolveRunListItem = {
  solve_run_id: number;
  run_kind: string;
  accepted_at: string;
  summary: SolveSummary;
};

export type TripWorkspace = {
  trip: TripDetail;
  workspace_version: number;
  candidates: Candidate[];
  rules: TripRule[];
  latest_accepted_run: SolvePayload | null;
  planning_summary: {
    updated_at: string;
    candidate_count: number;
    rule_count: number;
  } | null;
};

export type ExecutionSession = {
  execution_session_id: number;
  active_run_id: number | null;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  current_stop_id: number | null;
};

export type ExecutionEvent = {
  event_id: number;
  event_type: string;
  payload: Record<string, unknown>;
  recorded_at: string;
};

export type ExecutionBootstrap = {
  trip: TripDetail;
  execution_session: ExecutionSession;
  active_solve: SolvePayload;
  events: ExecutionEvent[];
  current_stop: SolveStop | null;
  next_stop: SolveStop | null;
  replan_readiness: {
    can_replan: boolean;
    reasons: string[];
  };
};

export type ExecutionStartResponse = {
  execution_session_id: number;
  trip_state: string;
  active_run_id: number;
};

export type ReplanAcceptedResponse = {
  execution_session_id: number;
  active_run_id: number;
  solve_run_id: number;
  accepted: boolean;
  solve: SolvePayload;
};
