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
  home: TeamFeatures;
  away: TeamFeatures;
  odds: { home: number | null; draw: number | null; away: number | null };
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
