"use client";

import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@/context/AuthContext";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── types ──────────────────────────────────────────────────────────────────────

interface Pool {
  id: number;
  week_code: string;
  status: string;
  match_count: number;
  locked_count: number;
  deadline_at: string | null;
  created_at: string | null;
}

interface MatchScore {
  p1: number; px: number; p2: number;
  primary_pick: string;
  secondary_pick: string | null;
  coverage_pick: string | null;
  confidence_score: number | null;
  coverage_need_score: number | null;
  reason_codes: string[];
  model_version: string;
}

interface PoolMatch {
  id: number;
  sequence_no: number;
  home_team: string;
  away_team: string;
  kickoff_at: string | null;
  status: string;
  is_locked: boolean;
  result: string | null;
  is_derby: boolean;
  admin_flags: Record<string, unknown>;
  score: MatchScore | null;
}

interface Features {
  strength_edge: number | null; form_edge: number | null; home_advantage: number | null;
  draw_tendency: number | null; balance_score: number | null; low_tempo_signal: number | null;
  low_goal_signal: number | null; draw_history: number | null; tactical_symmetry: number | null;
  lineup_continuity: number | null; market_support: number | null; volatility_score: number | null;
  lineup_penalty_home: number | null; lineup_penalty_away: number | null; lineup_certainty: number | null;
  h2h_home_win_rate: number | null; h2h_away_win_rate: number | null; h2h_draw_rate: number | null;
  h2h_venue_home_win_rate: number | null; h2h_bogey_flag: boolean | null; h2h_sample_size: number | null;
  rest_days_home_actual: number | null; rest_days_away_actual: number | null;
  post_intl_break_home: boolean | null; post_intl_break_away: boolean | null;
  congestion_risk_home: boolean | null; congestion_risk_away: boolean | null;
  is_derby: boolean | null; derby_confidence_suppressor: number | null;
  opening_odds_home: number | null; opening_odds_away: number | null; opening_odds_draw: number | null;
  odds_delta_home: number | null; sharp_money_signal: number | null;
  away_form_home: number | null; away_form_away: number | null;
  xg_proxy_home: number | null; xg_proxy_away: number | null;
  xg_luck_home: number | null; xg_luck_away: number | null;
  lucky_form_home: boolean | null; lucky_form_away: boolean | null;
  unlucky_form_home: boolean | null; unlucky_form_away: boolean | null;
  motivation_home: number | null; motivation_away: number | null;
  points_above_relegation_home: number | null; points_above_relegation_away: number | null;
  points_to_top4_home: number | null; points_to_top4_away: number | null;
  points_to_top6_home: number | null; points_to_top6_away: number | null;
  points_to_title_home: number | null; points_to_title_away: number | null;
  long_unbeaten_home: boolean | null; long_unbeaten_away: boolean | null;
  key_attacker_absent_home: boolean | null; key_attacker_absent_away: boolean | null;
  key_defender_absent_home: boolean | null; key_defender_absent_away: boolean | null;
  home: Record<string, number | null> | null;
  away: Record<string, number | null> | null;
  odds_snapshots: { snapshot_time: string; home: number | null; draw: number | null; away: number | null }[];
}

interface MatchDetail {
  id: number; sequence_no: number; home_team: string; away_team: string;
  kickoff_at: string | null; status: string; is_locked: boolean;
  result: string | null; is_derby: boolean; admin_flags: Record<string, unknown>;
  latest_score: MatchScore | null;
  score_history: {
    created_at: string; p1: number; px: number; p2: number;
    primary_pick: string; secondary_pick: string | null;
    coverage_pick: string | null; confidence_score: number | null;
    coverage_need_score: number | null; model_version: string; reason_codes: string[];
  }[];
  features: Features | null;
  h2h: {
    kickoff_at: string | null; home_team: string; away_team: string;
    home_score: number | null; away_score: number | null;
    result_from_home_perspective: string;
  }[];
  changes: {
    id: number; created_at: string;
    old_primary_pick: string | null; new_primary_pick: string | null;
    old_coverage_pick: string | null; new_coverage_pick: string | null;
    change_reason_code: string | null; triggered_by: string | null;
  }[];
}

// ── helpers ────────────────────────────────────────────────────────────────────

function pct(v: number | null | undefined) {
  if (v == null) return "—";
  return `${(v * 100).toFixed(1)}%`;
}
function num(v: number | null | undefined, dp = 2) {
  if (v == null) return "—";
  return v.toFixed(dp);
}
function bool(v: boolean | null | undefined) {
  if (v == null) return <span className="text-zinc-500">—</span>;
  return v
    ? <span className="text-emerald-400 font-bold">✓</span>
    : <span className="text-zinc-600">✗</span>;
}
function pickColor(p: string | null | undefined) {
  if (p === "1") return "bg-blue-600 text-white";
  if (p === "X") return "bg-amber-500 text-black";
  if (p === "2") return "bg-red-600 text-white";
  return "bg-zinc-700 text-zinc-200";
}
function statusDot(s: string) {
  const c = s === "open" ? "bg-emerald-400" : s === "locked" ? "bg-red-400" : "bg-zinc-400";
  return <span className={`inline-block w-2 h-2 rounded-full ${c} mr-1.5`} />;
}

function Bar({ v }: { v: number | null }) {
  if (v == null) return <div className="h-1.5 w-full bg-zinc-700 rounded" />;
  const p = Math.round(Math.max(0, Math.min(1, v)) * 100);
  const color = p > 66 ? "bg-emerald-400" : p > 33 ? "bg-amber-400" : "bg-red-500";
  return (
    <div className="h-1.5 w-full bg-zinc-700 rounded overflow-hidden">
      <div className={`h-full ${color}`} style={{ width: `${p}%` }} />
    </div>
  );
}

function ProbRow({ p1, px, p2, pick }: { p1: number; px: number; p2: number; pick: string | null }) {
  const t = p1 + px + p2 || 1;
  return (
    <div className="flex gap-1 text-xs font-mono">
      <span className={`px-1.5 py-0.5 rounded ${pick === "1" ? "bg-blue-600 text-white" : "bg-zinc-700 text-zinc-300"}`}>
        1 {(p1 / t * 100).toFixed(0)}%
      </span>
      <span className={`px-1.5 py-0.5 rounded ${pick === "X" ? "bg-amber-500 text-black" : "bg-zinc-700 text-zinc-300"}`}>
        X {(px / t * 100).toFixed(0)}%
      </span>
      <span className={`px-1.5 py-0.5 rounded ${pick === "2" ? "bg-red-600 text-white" : "bg-zinc-700 text-zinc-300"}`}>
        2 {(p2 / t * 100).toFixed(0)}%
      </span>
    </div>
  );
}

function SH({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[10px] font-bold tracking-widest uppercase text-zinc-500 border-b border-zinc-700 pb-1 mb-2 mt-5 first:mt-0">
      {children}
    </div>
  );
}

function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex justify-between items-center py-0.5 text-xs border-b border-zinc-800">
      <span className="text-zinc-400">{k}</span>
      <span className="text-zinc-100 font-mono">{v}</span>
    </div>
  );
}

function DKV({ k, home, away }: { k: string; home: React.ReactNode; away: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[1fr_auto_auto] gap-x-3 items-center py-0.5 text-xs border-b border-zinc-800">
      <span className="text-zinc-400">{k}</span>
      <span className="text-blue-300 font-mono text-right w-16">{home}</span>
      <span className="text-red-300 font-mono text-right w-16">{away}</span>
    </div>
  );
}

// ── fetch hook ─────────────────────────────────────────────────────────────────

function useAdminFetch() {
  const { token } = useAuth();
  return useCallback(
    async (path: string, opts: RequestInit = {}) => {
      const res = await fetch(`${BASE}${path}`, {
        ...opts,
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
          ...(opts.headers ?? {}),
        },
      });
      if (!res.ok) throw new Error((await res.json()).detail ?? res.statusText);
      return res.json();
    },
    [token]
  );
}

// ── match detail slide-over ────────────────────────────────────────────────────

function MatchDetailPanel({ poolId, matchId, onClose }: { poolId: number; matchId: number; onClose: () => void }) {
  const apiFetch = useAdminFetch();
  const [data, setData] = useState<MatchDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<"signals" | "h2h" | "history" | "ops">("signals");
  const [msg, setMsg] = useState<string | null>(null);
  const [overrideForm, setOverrideForm] = useState({ primary: "1", coverage: "1", reason: "" });
  const [flagForm, setFlagForm] = useState({ is_derby: false, thursday_european_away: false });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const d: MatchDetail = await apiFetch(`/admin/pools/${poolId}/matches/${matchId}`);
      setData(d);
      setFlagForm({
        is_derby: !!d.is_derby,
        thursday_european_away: !!(d.admin_flags?.thursday_european_away),
      });
    } catch (e: unknown) { setMsg(`Yüklenemedi: ${(e as Error).message}`); }
    finally { setLoading(false); }
  }, [apiFetch, poolId, matchId]);

  useEffect(() => { load(); }, [load]);

  async function recompute() {
    try {
      const r = await apiFetch(`/admin/recompute-match/${matchId}`, { method: "POST" });
      setMsg(r.detail ?? "Yeniden hesaplandı"); load();
    } catch (e: unknown) { setMsg((e as Error).message); }
  }

  async function saveFlags() {
    try {
      const r = await apiFetch(`/admin/pools/${poolId}/matches/${matchId}/flags`, {
        method: "POST",
        body: JSON.stringify({ is_derby: flagForm.is_derby, thursday_european_away: flagForm.thursday_european_away }),
      });
      setMsg(r.detail ?? "Güncellendi"); load();
    } catch (e: unknown) { setMsg((e as Error).message); }
  }

  async function applyOverride() {
    if (!data) return;
    try {
      const r = await apiFetch("/admin/manual-override", {
        method: "POST",
        body: JSON.stringify({
          weekly_pool_match_id: matchId,
          primary_pick: overrideForm.primary,
          coverage_pick: overrideForm.coverage,
          reason: overrideForm.reason || "manual_override",
        }),
      });
      setMsg(r.detail ?? "Uygulandı"); load();
    } catch (e: unknown) { setMsg((e as Error).message); }
  }

  const f = data?.features;
  const s = data?.latest_score;
  const TABS = [
    { id: "signals" as const, label: "Sinyaller" },
    { id: "h2h" as const, label: "H2H" },
    { id: "history" as const, label: "Tarih" },
    { id: "ops" as const, label: "İşlemler" },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-stretch justify-end bg-black/70 backdrop-blur-sm" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="w-full max-w-2xl bg-zinc-900 border-l border-zinc-700 flex flex-col overflow-hidden shadow-2xl">
        {/* header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-zinc-700 bg-zinc-950 shrink-0">
          {loading ? <div className="h-5 w-48 bg-zinc-700 rounded animate-pulse" /> : (
            <div className="flex items-center gap-2 flex-1 min-w-0">
              <span className="text-xs font-mono text-zinc-500 shrink-0">#{data?.sequence_no}</span>
              {data?.is_derby && <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-orange-600 text-white shrink-0">DERBY</span>}
              {data?.is_locked && <span className="px-1.5 py-0.5 rounded text-[10px] bg-red-900 text-red-200 shrink-0">KİLİTLİ</span>}
              <span className="text-sm font-semibold text-white truncate">{data?.home_team} <span className="text-zinc-500">vs</span> {data?.away_team}</span>
            </div>
          )}
          <button onClick={onClose} className="text-zinc-400 hover:text-white text-2xl leading-none ml-4 shrink-0">×</button>
        </div>

        {/* score strip */}
        {s && (
          <div className="px-5 py-2 bg-zinc-800 border-b border-zinc-700 flex items-center gap-3 flex-wrap shrink-0">
            <ProbRow p1={s.p1} px={s.px} p2={s.p2} pick={s.primary_pick} />
            <div className="ml-auto flex items-center gap-3 text-xs flex-wrap">
              <span className="text-zinc-400">Güven <span className="text-white font-mono">{s.confidence_score?.toFixed(0) ?? "—"}</span></span>
              <span className="text-zinc-400">Kapsam <span className={`px-1.5 py-0.5 rounded font-mono ${pickColor(s.coverage_pick)}`}>{s.coverage_pick ?? "—"}</span></span>
              {s.coverage_need_score != null && (
                <span className="text-zinc-400">Risk <span className="text-white font-mono">{s.coverage_need_score.toFixed(0)}</span></span>
              )}
              <span className="text-zinc-600 font-mono text-[10px]">{s.model_version}</span>
            </div>
          </div>
        )}

        {/* reason codes */}
        {s && s.reason_codes.length > 0 && (
          <div className="px-5 py-1.5 border-b border-zinc-700 flex flex-wrap gap-1 shrink-0">
            {s.reason_codes.map(rc => (
              <span key={rc} className="px-1.5 py-0.5 rounded text-[10px] bg-zinc-700 text-zinc-300 font-mono">{rc}</span>
            ))}
          </div>
        )}

        {msg && (
          <div className="px-5 py-2 text-xs bg-emerald-950/40 text-emerald-300 border-b border-emerald-800 shrink-0">
            {msg} <button onClick={() => setMsg(null)} className="ml-2 text-emerald-500">×</button>
          </div>
        )}

        {/* tabs */}
        <div className="flex border-b border-zinc-700 shrink-0 bg-zinc-950">
          {TABS.map(t => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`px-5 py-2 text-xs font-semibold transition-colors ${tab === t.id ? "border-b-2 border-blue-500 text-white" : "text-zinc-500 hover:text-zinc-300"}`}>
              {t.label}
            </button>
          ))}
        </div>

        {/* body */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {loading ? (
            <div className="space-y-2">{[...Array(10)].map((_, i) => (
              <div key={i} className="h-4 bg-zinc-800 rounded animate-pulse" style={{ width: `${55 + (i * 17 % 45)}%` }} />
            ))}</div>
          ) : (
            <>
              {/* SIGNALS */}
              {tab === "signals" && (
                <>
                  {!f ? (
                    <p className="text-zinc-500 text-sm">Bu maç için henüz özellik hesaplanmamış.</p>
                  ) : (
                    <>
                      <div className="grid grid-cols-[1fr_auto_auto] gap-x-3 text-[10px] font-bold uppercase tracking-widest text-zinc-600 border-b border-zinc-700 pb-1 mb-1">
                        <span>Sinyal</span><span className="text-blue-500 w-16 text-right">EV</span><span className="text-red-500 w-16 text-right">DEP</span>
                      </div>

                      <SH>Takım Gücü</SH>
                      <DKV k="Güç skoru" home={pct(f.home?.strength_score)} away={pct(f.away?.strength_score)} />
                      <DKV k="Form skoru" home={pct(f.home?.form_score)} away={pct(f.away?.form_score)} />
                      <DKV k="PPG (sezon)" home={num(f.home?.season_ppg)} away={num(f.away?.season_ppg)} />
                      <DKV k="Gol farkı/maç" home={num(f.home?.goal_diff_per_game)} away={num(f.away?.goal_diff_per_game)} />
                      <DKV k="Atak indeksi" home={pct(f.home?.attack_index)} away={pct(f.away?.attack_index)} />
                      <DKV k="Savunma indeksi" home={pct(f.home?.defense_index)} away={pct(f.away?.defense_index)} />
                      <KV k="Güç farkı (ev+)" v={num(f.strength_edge)} />
                      <KV k="Form farkı (ev+)" v={num(f.form_edge)} />
                      <KV k="Ev avantajı" v={pct(f.home_advantage)} />

                      <SH>Motivasyon</SH>
                      <DKV k="Motivasyon" home={pct(f.motivation_home)} away={pct(f.motivation_away)} />
                      <DKV k="Puan/düşme hattı" home={f.points_above_relegation_home ?? "—"} away={f.points_above_relegation_away ?? "—"} />
                      <DKV k="Puan/şampiyonluk" home={f.points_to_title_home ?? "—"} away={f.points_to_title_away ?? "—"} />
                      <DKV k="Puan/Top 4" home={f.points_to_top4_home ?? "—"} away={f.points_to_top4_away ?? "—"} />
                      <DKV k="Puan/Top 6" home={f.points_to_top6_home ?? "—"} away={f.points_to_top6_away ?? "—"} />
                      <DKV k="Uzun yenilmezlik" home={bool(f.long_unbeaten_home)} away={bool(f.long_unbeaten_away)} />

                      <SH>Form & xG</SH>
                      <DKV k="Deplasman formu" home={pct(f.away_form_home)} away={pct(f.away_form_away)} />
                      <DKV k="xG proxy" home={num(f.xg_proxy_home)} away={num(f.xg_proxy_away)} />
                      <DKV k="xG şans farkı" home={num(f.xg_luck_home)} away={num(f.xg_luck_away)} />
                      <DKV k="Şanslı form" home={bool(f.lucky_form_home)} away={bool(f.lucky_form_away)} />
                      <DKV k="Şanssız form" home={bool(f.unlucky_form_home)} away={bool(f.unlucky_form_away)} />

                      <SH>Maç Analizi</SH>
                      <KV k="Beraberlik eğilimi" v={<span className="flex items-center gap-2"><Bar v={f.draw_tendency} />{pct(f.draw_tendency)}</span>} />
                      <KV k="Denge skoru" v={pct(f.balance_score)} />
                      <KV k="Düşük tempo" v={pct(f.low_tempo_signal)} />
                      <KV k="Az gol (u2.5)" v={pct(f.low_goal_signal)} />
                      <KV k="Beraberlik geçmişi" v={pct(f.draw_history)} />
                      <KV k="Taktik simetri" v={pct(f.tactical_symmetry)} />
                      <KV k="Piyasa desteği" v={pct(f.market_support)} />
                      <KV k="Volatilite" v={pct(f.volatility_score)} />

                      <SH>Kadro & Sakatlık</SH>
                      <KV k="Kadro sürekliliği" v={pct(f.lineup_continuity)} />
                      <KV k="Kadro kesinliği" v={pct(f.lineup_certainty)} />
                      <DKV k="Ceza (sakatlık)" home={pct(f.lineup_penalty_home)} away={pct(f.lineup_penalty_away)} />
                      <DKV k="Anahtar forvet yok" home={bool(f.key_attacker_absent_home)} away={bool(f.key_attacker_absent_away)} />
                      <DKV k="Anahtar defans yok" home={bool(f.key_defender_absent_home)} away={bool(f.key_defender_absent_away)} />

                      <SH>Program & Bağlam</SH>
                      <DKV k="Dinlenme günü" home={`${num(f.rest_days_home_actual, 0)} gün`} away={`${num(f.rest_days_away_actual, 0)} gün`} />
                      <DKV k="Milli ara sonrası" home={bool(f.post_intl_break_home)} away={bool(f.post_intl_break_away)} />
                      <DKV k="Yoğun program" home={bool(f.congestion_risk_home)} away={bool(f.congestion_risk_away)} />
                      <KV k="Derby" v={bool(f.is_derby)} />
                      <KV k="Derby baskıcı" v={num(f.derby_confidence_suppressor)} />

                      <SH>H2H İstatistik</SH>
                      <KV k="Örneklem (maç)" v={f.h2h_sample_size ?? "—"} />
                      <KV k="Ev galibiyet %" v={pct(f.h2h_home_win_rate)} />
                      <KV k="Dep galibiyet %" v={pct(f.h2h_away_win_rate)} />
                      <KV k="Beraberlik %" v={pct(f.h2h_draw_rate)} />
                      <KV k="Bu stadyumda ev %" v={pct(f.h2h_venue_home_win_rate)} />
                      <KV k="Bogey bayrağı" v={bool(f.h2h_bogey_flag)} />

                      <SH>Oranlar & Piyasa</SH>
                      {f.opening_odds_home != null ? (
                        <>
                          <KV k="Açılış ev" v={num(f.opening_odds_home)} />
                          <KV k="Açılış beraberlik" v={num(f.opening_odds_draw)} />
                          <KV k="Açılış deplasman" v={num(f.opening_odds_away)} />
                          <KV k="Ev oranı delta" v={num(f.odds_delta_home)} />
                          <KV k="Sharp money" v={
                            <span className={(f.sharp_money_signal ?? 0) > 0.3 ? "text-red-400" : (f.sharp_money_signal ?? 0) < -0.3 ? "text-blue-400" : ""}>
                              {num(f.sharp_money_signal)}
                            </span>
                          } />
                        </>
                      ) : <p className="text-xs text-zinc-600 py-1">Oran snapshot yok.</p>}

                      {f.odds_snapshots?.length > 0 && (
                        <div className="mt-3 overflow-x-auto">
                          <div className="text-[10px] text-zinc-500 mb-1">Oran hareketi ({f.odds_snapshots.length} snapshot)</div>
                          <table className="w-full text-[10px] font-mono">
                            <thead><tr className="text-zinc-600">
                              <th className="text-left pr-3">Zaman</th>
                              <th className="text-right pr-2">Ev</th>
                              <th className="text-right pr-2">Ber</th>
                              <th className="text-right">Dep</th>
                            </tr></thead>
                            <tbody>
                              {f.odds_snapshots.map((snap, i) => (
                                <tr key={i} className="border-t border-zinc-800">
                                  <td className="text-zinc-500 pr-3">{new Date(snap.snapshot_time).toLocaleString("tr-TR", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</td>
                                  <td className="text-blue-300 text-right pr-2">{snap.home?.toFixed(2) ?? "—"}</td>
                                  <td className="text-amber-300 text-right pr-2">{snap.draw?.toFixed(2) ?? "—"}</td>
                                  <td className="text-red-300 text-right">{snap.away?.toFixed(2) ?? "—"}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </>
                  )}
                </>
              )}

              {/* H2H */}
              {tab === "h2h" && (
                <div>
                  {!data?.h2h.length ? (
                    <p className="text-zinc-500 text-sm">H2H verisi yok.</p>
                  ) : (
                    <div className="space-y-2">
                      {data.h2h.map((m, i) => {
                        const rc = m.result_from_home_perspective === "W" ? "bg-emerald-700 text-white"
                          : m.result_from_home_perspective === "L" ? "bg-red-800 text-white"
                          : "bg-amber-700 text-black";
                        return (
                          <div key={i} className="flex items-center gap-3 bg-zinc-800 rounded px-3 py-2 text-xs">
                            <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${rc}`}>{m.result_from_home_perspective}</span>
                            <span className="text-zinc-300 flex-1 truncate">{m.home_team} <span className="text-zinc-500">vs</span> {m.away_team}</span>
                            <span className="font-mono text-white shrink-0">{m.home_score ?? "?"}-{m.away_score ?? "?"}</span>
                            <span className="text-zinc-500 shrink-0">{m.kickoff_at ? new Date(m.kickoff_at).toLocaleDateString("tr-TR") : "?"}</span>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}

              {/* HISTORY */}
              {tab === "history" && (
                <div>
                  <SH>Skor Geçmişi</SH>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs font-mono">
                      <thead><tr className="text-zinc-500 text-[10px]">
                        <th className="text-left pr-3 pb-1">Zaman</th>
                        <th className="pr-1 pb-1">1</th><th className="pr-1 pb-1">X</th><th className="pr-2 pb-1">2</th>
                        <th className="pr-2 pb-1">Tahmin</th><th className="pr-2 pb-1">Kapsam</th>
                        <th className="pr-2 pb-1">Güven</th><th className="pb-1">Model</th>
                      </tr></thead>
                      <tbody>
                        {data?.score_history.map((sh, i) => (
                          <tr key={i} className={`border-t border-zinc-800 ${i === 0 ? "text-white" : "text-zinc-400"}`}>
                            <td className="pr-3 py-0.5 text-zinc-500 text-[10px]">{new Date(sh.created_at).toLocaleString("tr-TR", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</td>
                            <td className="pr-1 text-blue-300">{(sh.p1 * 100).toFixed(0)}%</td>
                            <td className="pr-1 text-amber-300">{(sh.px * 100).toFixed(0)}%</td>
                            <td className="pr-2 text-red-300">{(sh.p2 * 100).toFixed(0)}%</td>
                            <td className="pr-2"><span className={`px-1 rounded ${pickColor(sh.primary_pick)}`}>{sh.primary_pick}</span></td>
                            <td className="pr-2"><span className={`px-1 rounded ${pickColor(sh.coverage_pick)}`}>{sh.coverage_pick ?? "—"}</span></td>
                            <td className="pr-2">{sh.confidence_score?.toFixed(0) ?? "—"}</td>
                            <td className="text-zinc-600 text-[10px]">{sh.model_version}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {!!data?.changes.length && (
                    <>
                      <SH>Değişiklik Günlüğü</SH>
                      <div className="space-y-1">
                        {data.changes.map(c => (
                          <div key={c.id} className="bg-zinc-800 rounded px-3 py-2 text-xs">
                            <div className="flex justify-between text-zinc-500 text-[10px] mb-0.5">
                              <span>{new Date(c.created_at).toLocaleString("tr-TR")}</span>
                              <span>{c.triggered_by}</span>
                            </div>
                            <div className="flex gap-2 flex-wrap items-center">
                              <span className="text-zinc-500">Tahmin:</span>
                              <span className={`px-1 rounded ${pickColor(c.old_primary_pick)}`}>{c.old_primary_pick ?? "—"}</span>
                              <span className="text-zinc-600">→</span>
                              <span className={`px-1 rounded ${pickColor(c.new_primary_pick)}`}>{c.new_primary_pick ?? "—"}</span>
                              {c.change_reason_code && (
                                <span className="px-1.5 rounded text-[10px] bg-zinc-700 text-zinc-400 font-mono">{c.change_reason_code}</span>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </>
                  )}
                </div>
              )}

              {/* OPS */}
              {tab === "ops" && (
                <div className="space-y-5">
                  <div className="bg-zinc-800 rounded-lg p-4">
                    <div className="text-xs font-semibold text-zinc-300 mb-1">Yeniden Hesapla</div>
                    <p className="text-xs text-zinc-500 mb-3">Tüm özellik + puanlama pipeline&apos;ını bu maç için çalıştırır.</p>
                    <button onClick={recompute} disabled={data?.is_locked}
                      className="px-4 py-1.5 bg-blue-700 hover:bg-blue-600 disabled:opacity-40 text-white text-xs rounded font-medium">
                      Yeniden Hesapla
                    </button>
                  </div>

                  <div className="bg-zinc-800 rounded-lg p-4">
                    <div className="text-xs font-semibold text-zinc-300 mb-3">Admin Bayrakları</div>
                    <label className="flex items-center gap-2 text-xs text-zinc-300 cursor-pointer mb-2">
                      <input type="checkbox" checked={flagForm.is_derby}
                        onChange={e => setFlagForm(f => ({ ...f, is_derby: e.target.checked }))}
                        className="accent-orange-500" />
                      Derby maçı
                    </label>
                    <label className="flex items-center gap-2 text-xs text-zinc-300 cursor-pointer mb-3">
                      <input type="checkbox" checked={flagForm.thursday_european_away}
                        onChange={e => setFlagForm(f => ({ ...f, thursday_european_away: e.target.checked }))}
                        className="accent-purple-500" />
                      Perşembe Avrupa (deplasman)
                    </label>
                    <button onClick={saveFlags} disabled={data?.is_locked}
                      className="px-4 py-1.5 bg-zinc-600 hover:bg-zinc-500 disabled:opacity-40 text-white text-xs rounded font-medium">
                      Kaydet
                    </button>
                  </div>

                  <div className="bg-zinc-800 rounded-lg p-4">
                    <div className="text-xs font-semibold text-zinc-300 mb-1">Manuel Geçersiz Kılma</div>
                    <p className="text-xs text-zinc-500 mb-3">Model skorunu override eder ve geçmişe kaydeder.</p>
                    <div className="grid grid-cols-2 gap-2 mb-2">
                      <div>
                        <label className="text-[10px] text-zinc-500 block mb-1">Ana Tahmin</label>
                        <select value={overrideForm.primary} onChange={e => setOverrideForm(f => ({ ...f, primary: e.target.value }))}
                          className="w-full bg-zinc-700 text-white text-xs rounded px-2 py-1.5">
                          {["1","X","2"].map(v => <option key={v}>{v}</option>)}
                        </select>
                      </div>
                      <div>
                        <label className="text-[10px] text-zinc-500 block mb-1">Kapsam</label>
                        <select value={overrideForm.coverage} onChange={e => setOverrideForm(f => ({ ...f, coverage: e.target.value }))}
                          className="w-full bg-zinc-700 text-white text-xs rounded px-2 py-1.5">
                          {["1","X","2","1X","X2","12","1X2"].map(v => <option key={v}>{v}</option>)}
                        </select>
                      </div>
                    </div>
                    <input placeholder="Neden (isteğe bağlı)" value={overrideForm.reason}
                      onChange={e => setOverrideForm(f => ({ ...f, reason: e.target.value }))}
                      className="w-full bg-zinc-700 text-white text-xs rounded px-2 py-1.5 mb-2 placeholder-zinc-500" />
                    <button onClick={applyOverride} disabled={data?.is_locked}
                      className="px-4 py-1.5 bg-red-800 hover:bg-red-700 disabled:opacity-40 text-white text-xs rounded font-medium">
                      Geçersiz Kılmayı Uygula
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ── pool match list ────────────────────────────────────────────────────────────

function PoolMatchList({ poolId, onSelect }: { poolId: number; onSelect: (id: number) => void }) {
  const apiFetch = useAdminFetch();
  const [matches, setMatches] = useState<PoolMatch[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    apiFetch(`/admin/pools/${poolId}`).then(setMatches).catch(() => {}).finally(() => setLoading(false));
  }, [apiFetch, poolId]);

  if (loading) return (
    <div className="p-4 space-y-2">{[...Array(15)].map((_, i) => (
      <div key={i} className="h-12 bg-zinc-800 rounded animate-pulse" />
    ))}</div>
  );

  return (
    <div className="divide-y divide-zinc-800">
      {matches.map(m => {
        const sc = m.score;
        return (
          <button key={m.id} onClick={() => onSelect(m.id)}
            className="w-full text-left px-4 py-3 hover:bg-zinc-800 transition-colors group">
            <div className="flex items-center gap-1.5 mb-1">
              <span className="text-zinc-500 text-xs font-mono w-5 shrink-0">{m.sequence_no}</span>
              {m.is_derby && <span className="text-[9px] px-1 rounded bg-orange-600 text-white font-bold shrink-0">D</span>}
              {m.is_locked && <span className="text-[9px] shrink-0">🔒</span>}
              <span className="text-xs text-white flex-1 truncate">{m.home_team} <span className="text-zinc-500 text-[10px]">vs</span> {m.away_team}</span>
              {m.result && <span className={`text-[10px] font-bold px-1 rounded ${pickColor(m.result)} shrink-0`}>{m.result}</span>}
            </div>
            <div className="flex items-center gap-2 pl-7">
              {sc ? (
                <>
                  <ProbRow p1={sc.p1} px={sc.px} p2={sc.p2} pick={sc.primary_pick} />
                  <span className="ml-auto text-[10px] text-zinc-600 font-mono shrink-0">{sc.confidence_score?.toFixed(0) ?? "—"}</span>
                </>
              ) : (
                <span className="text-[10px] text-zinc-700">skor yok</span>
              )}
            </div>
          </button>
        );
      })}
    </div>
  );
}

// ── main page ──────────────────────────────────────────────────────────────────

export default function AdminPage() {
  const { token, login } = useAuth();
  const apiFetch = useAdminFetch();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authError, setAuthError] = useState<string | null>(null);

  const [pools, setPools] = useState<Pool[]>([]);
  const [selectedPool, setSelectedPool] = useState<number | null>(null);
  const [selectedMatch, setSelectedMatch] = useState<number | null>(null);
  const [sidebarTab, setSidebarTab] = useState<"matches" | "ops">("matches");

  const [weekCode, setWeekCode] = useState("");
  const [fixtureIds, setFixtureIds] = useState("");
  const [opsMsg, setOpsMsg] = useState<string | null>(null);

  interface ResolvedFixture {
    seq: number; date: string;
    home_input: string; away_input: string;
    matched: boolean; fixture_id: number | null;
    home_found: string | null; away_found: string | null;
    confidence: number;
    candidates: { fixture_id: number; home: string; away: string; confidence: number }[];
  }
  const [rawMatchList, setRawMatchList] = useState("");
  const [resolveWeekCode, setResolveWeekCode] = useState("");

  function isoWeekFromText(text: string): string {
    const m = text.match(/(\d{2})\.(\d{2})\.(\d{4})/);
    if (!m) return "";
    const date = new Date(parseInt(m[3]), parseInt(m[2]) - 1, parseInt(m[1]));
    const thu = new Date(date); thu.setDate(date.getDate() - (date.getDay() + 6) % 7 + 3);
    const jan4 = new Date(thu.getFullYear(), 0, 4);
    const week = 1 + Math.round((thu.getTime() - jan4.getTime()) / 604800000);
    return `${thu.getFullYear()}-W${String(week).padStart(2, "0")}`;
  }
  const [resolvedMatches, setResolvedMatches] = useState<ResolvedFixture[]>([]);
  const [resolveLoading, setResolveLoading] = useState(false);
  const [rowOverrides, setRowOverrides] = useState<Record<number, number | null>>({});

  const loadPools = useCallback(async () => {
    try {
      const data: Pool[] = await apiFetch("/admin/pools");
      setPools(data);
      if (data.length > 0) setSelectedPool(p => p ?? data[0].id);
    } catch {}
  }, [apiFetch]);

  useEffect(() => { if (token) loadPools(); }, [token, loadPools]);

  async function doLogin(e: React.FormEvent) {
    e.preventDefault();
    setAuthError(null);
    try {
      const res = await fetch(`${BASE}/auth/login`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await res.json();
      if (!res.ok) { setAuthError(data.detail ?? "Giriş başarısız"); return; }
      login(data.access_token);
    } catch { setAuthError("Sunucuya bağlanılamadı"); }
  }

  async function importWeek() {
    const ids = fixtureIds.split(",").map(s => parseInt(s.trim())).filter(Boolean);
    try {
      const r = await apiFetch("/admin/weekly-import", {
        method: "POST", body: JSON.stringify({ week_code: weekCode, fixture_external_ids: ids }),
      });
      setOpsMsg(`${r.detail} — task: ${r.task_id}`);
    } catch (e: unknown) { setOpsMsg((e as Error).message); }
  }

  async function resolveList() {
    setResolveLoading(true);
    setResolvedMatches([]);
    setRowOverrides({});
    try {
      const data = await apiFetch("/admin/fixtures/resolve-list", {
        method: "POST",
        body: JSON.stringify({ raw_text: rawMatchList, week_code: resolveWeekCode }),
      });
      setResolvedMatches(data.resolved);
    } catch (e: unknown) { setOpsMsg((e as Error).message); }
    finally { setResolveLoading(false); }
  }

  async function importResolved() {
    const ids = resolvedMatches
      .map(m => rowOverrides[m.seq] !== undefined ? rowOverrides[m.seq] : m.fixture_id)
      .filter((id): id is number => id != null);
    try {
      const r = await apiFetch("/admin/weekly-import", {
        method: "POST",
        body: JSON.stringify({ week_code: resolveWeekCode, fixture_external_ids: ids }),
      });
      setOpsMsg(`${r.detail} — task: ${r.task_id}`);
    } catch (e: unknown) { setOpsMsg((e as Error).message); }
  }

  async function recomputePool() {
    if (!selectedPool) return;
    try {
      const r = await apiFetch(`/admin/recompute-week/${selectedPool}`, { method: "POST" });
      setOpsMsg(`${r.detail} — task: ${r.task_id}`);
    } catch (e: unknown) { setOpsMsg((e as Error).message); }
  }

  // ── login ──────────────────────────────────────────────────────────────────
  if (!token) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center p-4">
        <div className="w-full max-w-sm bg-zinc-900 border border-zinc-700 rounded-xl p-8 shadow-2xl">
          <div className="text-center mb-6">
            <div className="text-2xl font-black tracking-tight text-white mb-1">STOTTO</div>
            <div className="text-xs text-zinc-500 uppercase tracking-widest">Admin Paneli</div>
          </div>
          <form onSubmit={doLogin} className="space-y-3">
            <input type="email" required placeholder="E-posta" value={email} onChange={e => setEmail(e.target.value)}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2.5 text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-blue-500" />
            <input type="password" required placeholder="Şifre" value={password} onChange={e => setPassword(e.target.value)}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2.5 text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-blue-500" />
            {authError && <p className="text-red-400 text-xs">{authError}</p>}
            <button type="submit" className="w-full bg-blue-600 hover:bg-blue-500 text-white font-semibold py-2.5 rounded-lg text-sm transition-colors">
              Giriş Yap
            </button>
          </form>
        </div>
      </div>
    );
  }

  // ── dashboard ──────────────────────────────────────────────────────────────
  const activePool = pools.find(p => p.id === selectedPool);

  return (
    <div className="min-h-screen bg-zinc-950 flex flex-col text-white">
      {/* topbar */}
      <header className="h-11 border-b border-zinc-800 flex items-center px-4 gap-3 shrink-0 bg-zinc-950">
        <span className="text-xs font-black tracking-widest text-white">STOTTO</span>
        <span className="text-[10px] uppercase tracking-widest text-zinc-600 border-l border-zinc-700 pl-3">Admin</span>
        <div className="ml-auto flex items-center gap-2">
          <select value={selectedPool ?? ""} onChange={e => { setSelectedPool(Number(e.target.value)); setSelectedMatch(null); }}
            className="bg-zinc-800 text-white text-xs rounded px-2 py-1 border border-zinc-700 max-w-52 truncate">
            {pools.map(p => (
              <option key={p.id} value={p.id}>{p.week_code} · {p.status} · {p.match_count} maç</option>
            ))}
          </select>
          {activePool && (
            <span className="text-[10px] font-mono text-zinc-600">
              {activePool.locked_count}/{activePool.match_count} kilitli
            </span>
          )}
        </div>
      </header>

      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* sidebar */}
        <aside className="w-72 shrink-0 border-r border-zinc-800 flex flex-col bg-zinc-900">
          <div className="flex border-b border-zinc-800 shrink-0">
            {(["matches", "ops"] as const).map(t => (
              <button key={t} onClick={() => setSidebarTab(t)}
                className={`flex-1 py-2.5 text-xs font-semibold transition-colors ${sidebarTab === t ? "border-b-2 border-blue-500 text-white" : "text-zinc-500 hover:text-zinc-300"}`}>
                {t === "matches" ? "Maçlar" : "İşlemler"}
              </button>
            ))}
          </div>

          <div className="flex-1 overflow-y-auto">
            {sidebarTab === "matches" && selectedPool && (
              <PoolMatchList poolId={selectedPool} onSelect={id => setSelectedMatch(id)} />
            )}

            {sidebarTab === "ops" && (
              <div className="p-4 space-y-5">
                {opsMsg && (
                  <div className="text-xs text-emerald-300 bg-emerald-950/40 border border-emerald-800 rounded p-2 break-all">
                    {opsMsg} <button onClick={() => setOpsMsg(null)} className="ml-1 text-emerald-500">×</button>
                  </div>
                )}

                <div>
                  <div className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 mb-2">Listeden İçe Aktar</div>
                  <input placeholder="Hafta kodu (örn: 2026-W15)" value={resolveWeekCode} onChange={e => setResolveWeekCode(e.target.value)}
                    className="w-full bg-zinc-800 text-white text-xs rounded px-2 py-1.5 mb-2 placeholder-zinc-600 border border-zinc-700" />
                  <textarea
                    placeholder={"Nesine.com maç listesini buraya yapıştırın…\n1\t10.04.2026 20:00\tBeşiktaş A.Ş.-Antalyaspor\n…"}
                    value={rawMatchList} onChange={e => { setRawMatchList(e.target.value); const wc = isoWeekFromText(e.target.value); if (wc) setResolveWeekCode(wc); }}
                    rows={5} className="w-full bg-zinc-800 text-white text-xs rounded px-2 py-1.5 mb-2 placeholder-zinc-600 border border-zinc-700 resize-none font-mono" />
                  <button onClick={resolveList} disabled={resolveLoading || !rawMatchList.trim()}
                    className="w-full py-1.5 bg-zinc-700 hover:bg-zinc-600 disabled:opacity-40 text-white text-xs rounded font-medium transition-colors mb-3">
                    {resolveLoading ? "Çözülüyor…" : "Çöz"}
                  </button>

                  {resolvedMatches.length > 0 && (() => {
                    const allResolved = resolvedMatches.every(m =>
                      (rowOverrides[m.seq] !== undefined ? rowOverrides[m.seq] : m.fixture_id) != null
                    );
                    const resolvedCount = resolvedMatches.filter(m =>
                      (rowOverrides[m.seq] !== undefined ? rowOverrides[m.seq] : m.fixture_id) != null
                    ).length;
                    return (
                      <div className="border border-zinc-700 rounded overflow-hidden mb-2">
                        <div className="max-h-80 overflow-y-auto divide-y divide-zinc-800">
                          {resolvedMatches.map(m => {
                            const effectiveId = rowOverrides[m.seq] !== undefined ? rowOverrides[m.seq] : m.fixture_id;
                            const rowColor = effectiveId != null
                              ? (m.matched ? "bg-emerald-950/30" : "bg-amber-950/30")
                              : "bg-red-950/30";
                            return (
                              <div key={m.seq} className={`px-2 py-1.5 text-xs ${rowColor}`}>
                                <div className="flex items-center gap-1.5 mb-1">
                                  <span className="text-zinc-500 font-mono w-4 shrink-0">{m.seq}</span>
                                  <span className="text-zinc-300 flex-1 truncate">{m.home_input} – {m.away_input}</span>
                                  {effectiveId != null
                                    ? <span className="font-mono text-zinc-400 shrink-0">{effectiveId}</span>
                                    : <span className="text-red-400 shrink-0">—</span>
                                  }
                                </div>
                                {m.matched && m.home_found && (
                                  <div className="text-[10px] text-emerald-400 pl-5 truncate">
                                    ✓ {m.home_found} – {m.away_found}
                                  </div>
                                )}
                                {!m.matched && m.candidates.length > 0 && (
                                  <select
                                    value={rowOverrides[m.seq] ?? ""}
                                    onChange={e => setRowOverrides(prev => ({ ...prev, [m.seq]: e.target.value ? parseInt(e.target.value) : null }))}
                                    className="mt-1 w-full bg-zinc-800 text-zinc-200 text-[10px] rounded px-1.5 py-1 border border-amber-700">
                                    <option value="">— seçin —</option>
                                    {m.candidates.map(c => (
                                      <option key={c.fixture_id} value={c.fixture_id}>
                                        {c.home} – {c.away} ({c.fixture_id})
                                      </option>
                                    ))}
                                  </select>
                                )}
                                {!m.matched && m.candidates.length === 0 && (
                                  <input type="number" placeholder="Fixture ID girin"
                                    value={rowOverrides[m.seq] ?? ""}
                                    onChange={e => setRowOverrides(prev => ({ ...prev, [m.seq]: e.target.value ? parseInt(e.target.value) : null }))}
                                    className="mt-1 w-full bg-zinc-800 text-zinc-200 text-[10px] rounded px-1.5 py-1 border border-red-700 placeholder-zinc-600" />
                                )}
                              </div>
                            );
                          })}
                        </div>
                        <button onClick={importResolved} disabled={!allResolved}
                          className="w-full py-1.5 bg-blue-700 hover:bg-blue-600 disabled:opacity-40 text-white text-xs font-medium transition-colors">
                          Tümünü İçe Aktar ({resolvedCount}/{resolvedMatches.length})
                        </button>
                      </div>
                    );
                  })()}
                </div>

                <div>
                  <div className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 mb-2">Haftalık İçe Aktar</div>
                  <input placeholder="Hafta kodu (örn: 2025-W15)" value={weekCode} onChange={e => setWeekCode(e.target.value)}
                    className="w-full bg-zinc-800 text-white text-xs rounded px-2 py-1.5 mb-2 placeholder-zinc-600 border border-zinc-700" />
                  <textarea placeholder="Fikstür ID'leri (virgülle ayrılmış)" value={fixtureIds} onChange={e => setFixtureIds(e.target.value)}
                    rows={3} className="w-full bg-zinc-800 text-white text-xs rounded px-2 py-1.5 mb-2 placeholder-zinc-600 border border-zinc-700 resize-none" />
                  <button onClick={importWeek}
                    className="w-full py-1.5 bg-blue-700 hover:bg-blue-600 text-white text-xs rounded font-medium transition-colors">
                    İçe Aktar
                  </button>
                </div>

                <div>
                  <div className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 mb-2">Haftayı Yeniden Hesapla</div>
                  <p className="text-xs text-zinc-600 mb-2">Seçili: {activePool?.week_code ?? "—"}</p>
                  <button onClick={recomputePool} disabled={!selectedPool}
                    className="w-full py-1.5 bg-zinc-700 hover:bg-zinc-600 disabled:opacity-40 text-white text-xs rounded font-medium transition-colors">
                    Yeniden Hesapla
                  </button>
                </div>

                <div className="border-t border-zinc-700 pt-4">
                  <div className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 mb-2">Tüm Haftalar</div>
                  <div className="space-y-1">
                    {pools.map(p => (
                      <button key={p.id} onClick={() => { setSelectedPool(p.id); setSidebarTab("matches"); setSelectedMatch(null); }}
                        className={`w-full flex items-center gap-2 px-2 py-1.5 rounded text-xs text-left transition-colors ${selectedPool === p.id ? "bg-blue-900/50 text-white" : "text-zinc-400 hover:bg-zinc-800"}`}>
                        {statusDot(p.status)}
                        <span className="font-mono flex-1">{p.week_code}</span>
                        <span className="text-zinc-600 text-[10px]">{p.match_count}m</span>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        </aside>

        {/* main area */}
        <main className="flex-1 overflow-auto flex items-center justify-center bg-zinc-950">
          {!selectedMatch && (
            <div className="text-center text-zinc-700 select-none">
              <div className="text-5xl mb-4">📊</div>
              <div className="text-sm font-medium">Analiz için bir maç seçin</div>
              <div className="text-xs mt-1 text-zinc-800">Sol panelden maça tıklayın</div>
            </div>
          )}
        </main>
      </div>

      {/* match detail slide-over */}
      {selectedMatch && selectedPool && (
        <MatchDetailPanel poolId={selectedPool} matchId={selectedMatch} onClose={() => setSelectedMatch(null)} />
      )}
    </div>
  );
}
