// NEXT_PUBLIC_API_URL is used by the browser (client-side).
// INTERNAL_API_URL is used by the Next.js server (SSR inside Docker where
// "localhost" would resolve to the frontend container, not the backend).
const BASE_URL =
  typeof window === "undefined"
    ? (process.env.INTERNAL_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000")
    : (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000");

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new ApiError(res.status, text);
  }
  return res.json() as Promise<T>;
}

export function get<T>(path: string): Promise<T> {
  return request<T>(path);
}

export function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "POST", body: JSON.stringify(body) });
}

export function authedGet<T>(path: string, token: string): Promise<T> {
  return request<T>(path, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function authedPost<T>(
  path: string,
  body: unknown,
  token: string
): Promise<T> {
  return request<T>(path, {
    method: "POST",
    body: JSON.stringify(body),
    headers: { Authorization: `Bearer ${token}` },
  });
}

// ── Types ──────────────────────────────────────────────────────────────────────

export interface MatchScore {
  p1: number;
  px: number;
  p2: number;
  primary_pick: string;
  secondary_pick: string | null;
  recommended_coverage: string | null;
  confidence_score: number | null;
  coverage_need_score: number | null;
  reason_codes: string[];
}

export interface PoolMatch {
  id: number;
  sequence_no: number;
  fixture_external_id: number;
  kickoff_at: string | null;
  status: string;
  is_locked: boolean;
  result: string | null;
  home_team: string;
  away_team: string;
  latest_score: MatchScore | null;
  is_derby: boolean;
  sharp_money_flag: boolean | null;
  post_intl_break: boolean | null;
}

export interface PoolSummary {
  id: number;
  week_code: string;
  status: string;
  announcement_time: string | null;
  deadline_at: string | null;
  match_count: number;
  locked_count: number;
}

export interface TeamFeatures {
  strength_score: number | null;
  form_score: number | null;
  season_ppg: number | null;
  goal_diff_per_game: number | null;
  attack_index: number | null;
  defense_index: number | null;
  raw: Record<string, unknown>;
}

export interface MatchFeatures {
  // v1
  strength_edge: number | null;
  form_edge: number | null;
  home_advantage: number | null;
  draw_tendency: number | null;
  balance_score: number | null;
  low_tempo_signal: number | null;
  low_goal_signal: number | null;
  draw_history: number | null;
  tactical_symmetry: number | null;
  lineup_continuity: number | null;
  market_support: number | null;
  volatility_score: number | null;
  lineup_penalty_home: number | null;
  lineup_penalty_away: number | null;
  lineup_certainty: number | null;
  // v2: H2H
  h2h_home_win_rate: number | null;
  h2h_away_win_rate: number | null;
  h2h_draw_rate: number | null;
  h2h_venue_home_win_rate: number | null;
  h2h_bogey_flag: boolean | null;
  h2h_sample_size: number | null;
  // v2: schedule
  rest_days_home_actual: number | null;
  rest_days_away_actual: number | null;
  post_intl_break_home: boolean | null;
  post_intl_break_away: boolean | null;
  congestion_risk_home: boolean | null;
  congestion_risk_away: boolean | null;
  // v2: derby
  is_derby: boolean | null;
  derby_confidence_suppressor: number | null;
  // v2: odds movement
  opening_odds_home: number | null;
  opening_odds_away: number | null;
  opening_odds_draw: number | null;
  odds_delta_home: number | null;
  sharp_money_signal: number | null;
  // v2: form
  away_form_home: number | null;
  away_form_away: number | null;
  // v2: xG
  xg_proxy_home: number | null;
  xg_proxy_away: number | null;
  xg_luck_home: number | null;
  xg_luck_away: number | null;
  lucky_form_home: boolean | null;
  lucky_form_away: boolean | null;
  unlucky_form_home: boolean | null;
  unlucky_form_away: boolean | null;
  // v2: motivation
  motivation_home: number | null;
  motivation_away: number | null;
  points_above_relegation_home: number | null;
  points_above_relegation_away: number | null;
  points_to_top4_home: number | null;
  points_to_top4_away: number | null;
  points_to_top6_home: number | null;
  points_to_top6_away: number | null;
  points_to_title_home: number | null;
  points_to_title_away: number | null;
  long_unbeaten_home: boolean | null;
  long_unbeaten_away: boolean | null;
  // v2: absences
  key_attacker_absent_home: boolean | null;
  key_attacker_absent_away: boolean | null;
  key_defender_absent_home: boolean | null;
  key_defender_absent_away: boolean | null;
  home: TeamFeatures;
  away: TeamFeatures;
  odds: { home: number | null; draw: number | null; away: number | null };
  odds_snapshots: { snapshot_time: string; home: number | null; draw: number | null; away: number | null }[];
  market: Record<string, unknown>;
}

export interface MatchDetail extends PoolMatch {
  score_history: ScoreHistory[];
  features: MatchFeatures | null;
}

export interface ScoreHistory {
  created_at: string;
  p1: number;
  px: number;
  p2: number;
  primary_pick: string;
  coverage_pick: string | null;
  confidence_score: number | null;
}

export interface CouponPick {
  pool_match_id: number;
  sequence_no: number;
  coverage_pick: string;
  coverage_type: string;
}

export interface CouponScenario {
  id: number;
  scenario_type: string;
  total_columns: number;
  expected_coverage_score: number | null;
  picks: CouponPick[];
}

export interface ScoreChange {
  id: number;
  created_at: string;
  sequence_no: number | null;
  old_primary_pick: string | null;
  new_primary_pick: string | null;
  old_coverage_pick: string | null;
  new_coverage_pick: string | null;
  change_reason_code: string | null;
  triggered_by: string | null;
}
