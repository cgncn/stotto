"use client";

import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";
import dynamic from "next/dynamic";
import { buildExplanation, safeVal } from "@/lib/explanation";
import { SkeletonCard, SkeletonBlock } from "@/components/Skeleton";
import ConfidenceRing from "@/components/ConfidenceRing";
import { SubscriberGate } from "@/components/SubscriberGate";
import { BlurPlaceholder } from "@/components/BlurPlaceholder";
import type { MatchFeatures } from "@/lib/api";

const RadarChart = dynamic(() => import("@/components/RadarChart"), { ssr: false });

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Constants ──────────────────────────────────────────────────────────────────

const BADGE: Record<string, string> = {
  "1":   "bg-blue-100 text-blue-800 border-blue-200",
  "X":   "bg-amber-100 text-amber-800 border-amber-200",
  "2":   "bg-red-100 text-red-800 border-red-200",
  "1X":  "bg-purple-100 text-purple-800 border-purple-200",
  "X2":  "bg-orange-100 text-orange-800 border-orange-200",
  "12":  "bg-green-100 text-green-800 border-green-200",
  "1X2": "bg-gray-700 text-white border-gray-700",
};

const H2H_PILL: Record<string, string> = {
  W: "bg-green-100 text-green-800",
  D: "bg-amber-100 text-amber-800",
  L: "bg-red-100 text-red-800",
  "?": "bg-gray-100 text-gray-500",
};

const REASON_LABEL: Record<string, string> = {
  HOME_STRENGTH: "Ev güçlü", AWAY_STRENGTH: "Dep. güçlü",
  HOME_FORM: "Ev formda", AWAY_FORM: "Dep. formda",
  DRAW_RISK: "Beraberlik riski", HOME_ABSENCE: "Ev eksik",
  AWAY_ABSENCE: "Dep. eksik", MARKET_ALIGNED: "Piyasa uyumlu",
  HIGH_VOLATILITY: "Yüksek volatilite", TRIPLE_RISK: "Üçlü gerekli",
  DERBY_FLAG: "Derby maçı", H2H_BOGEY: "Bogey takım",
  H2H_HOME_DOMINANT: "H2H ev üstün", POST_INTL_BREAK: "Milli ara",
  SHARP_MONEY_AWAY: "Sharp → Dep", SHARP_MONEY_HOME: "Sharp → Ev",
  LUCKY_FORM_HOME: "Ev şanslı form", LUCKY_FORM_AWAY: "Dep. şanslı form",
  UNLUCKY_FORM_HOME: "Ev şanssız form", UNLUCKY_FORM_AWAY: "Dep. şanssız form",
  HIGH_MOTIVATION_HOME: "Ev yüksek motivasyon", HIGH_MOTIVATION_AWAY: "Dep. yüksek motivasyon",
  CONGESTION_RISK_AWAY: "Dep. yoğun program", KEY_ATTACKER_ABSENT: "Anahtar forvet yok",
  KEY_DEFENDER_ABSENT: "Anahtar defans yok", LONG_UNBEATEN_HOME: "Uzun yenilmezlik (ev)",
  HOME_STRONG_AT_HOME: "Evde güçlü form",
};

// ── Sub-components ─────────────────────────────────────────────────────────────

function ProbBar({ p1, px, p2, primary }: { p1: number; px: number; p2: number; primary: string }) {
  return (
    <div>
      <div className="flex h-6 rounded-lg overflow-hidden">
        <div className="bg-blue-500 flex items-center justify-center text-white text-xs font-bold" style={{ width: `${p1 * 100}%` }}>
          {p1 > 0.13 && "1"}
        </div>
        <div className="bg-amber-400 flex items-center justify-center text-white text-xs font-bold" style={{ width: `${px * 100}%` }}>
          {px > 0.1 && "X"}
        </div>
        <div className="bg-red-500 flex items-center justify-center text-white text-xs font-bold" style={{ width: `${p2 * 100}%` }}>
          {p2 > 0.13 && "2"}
        </div>
      </div>
      <div className="flex justify-between text-sm mt-1.5 font-semibold">
        <span className={primary === "1" ? "text-blue-700" : "text-gray-500"}>{(p1 * 100).toFixed(1)}%</span>
        <span className={primary === "X" ? "text-amber-600" : "text-gray-500"}>{(px * 100).toFixed(1)}%</span>
        <span className={primary === "2" ? "text-red-600" : "text-gray-500"}>{(p2 * 100).toFixed(1)}%</span>
      </div>
    </div>
  );
}

function Gauge({ label, value, description, invert = false }: {
  label: string; value: number | null | undefined; description?: string; invert?: boolean;
}) {
  const raw = safeVal(value);
  const display = invert && raw != null ? 1 - raw : raw;
  const pct = display != null ? Math.max(0, Math.min(100, display * 100)) : null;
  const color = pct == null ? "bg-gray-200" : pct > 65 ? "bg-green-500" : pct > 38 ? "bg-amber-400" : "bg-red-400";
  return (
    <div className="bg-gray-50 rounded-lg p-3">
      <div className="flex justify-between items-baseline mb-1">
        <span className="text-xs text-gray-500 leading-tight">{label}</span>
        <span className="text-sm font-bold text-gray-700 ml-1">{pct != null ? pct.toFixed(0) : "—"}</span>
      </div>
      <div className="w-full bg-gray-200 rounded-full h-1.5">
        {pct != null && <div className={`${color} h-1.5 rounded-full transition-all`} style={{ width: `${pct}%` }} />}
      </div>
      {description && <p className="text-[10px] text-gray-400 mt-1 leading-snug">{description}</p>}
      {pct == null && <p className="text-[10px] text-amber-500 mt-1">Veri bekleniyor</p>}
    </div>
  );
}

function StatRow({ label, homeVal, awayVal, homeLabel, awayLabel, fmt: fmtFn = (v: number) => v.toFixed(2), higherIsBetter = true }: {
  label: string; homeVal: number | null | undefined; awayVal: number | null | undefined;
  homeLabel: string; awayLabel: string; fmt?: (v: number) => string; higherIsBetter?: boolean;
}) {
  const hv = homeVal ?? null;
  const av = awayVal ?? null;
  if (hv == null && av == null) return null;
  const max = Math.max(hv ?? 0, av ?? 0, 0.001);
  const homeWins = hv != null && av != null ? (higherIsBetter ? hv >= av : hv <= av) : null;
  return (
    <div className="py-2 border-b border-gray-50 last:border-0">
      <div className="flex justify-between text-xs text-gray-400 mb-1">
        <span className={`font-semibold ${homeWins === true ? "text-blue-700" : homeWins === false ? "text-gray-500" : "text-gray-600"}`}>
          {hv != null ? fmtFn(hv) : "—"}
        </span>
        <span className="text-gray-400">{label}</span>
        <span className={`font-semibold ${homeWins === false ? "text-red-600" : homeWins === true ? "text-gray-500" : "text-gray-600"}`}>
          {av != null ? fmtFn(av) : "—"}
        </span>
      </div>
      <div className="flex gap-1">
        <div className="flex-1 flex justify-end">
          {hv != null && <div className={`h-1.5 rounded-full ${homeWins === true ? "bg-blue-400" : "bg-gray-200"}`} style={{ width: `${(hv / max) * 100}%` }} />}
        </div>
        <div className="w-1" />
        <div className="flex-1">
          {av != null && <div className={`h-1.5 rounded-full ${homeWins === false ? "bg-red-400" : "bg-gray-200"}`} style={{ width: `${(av / max) * 100}%` }} />}
        </div>
      </div>
      <div className="flex justify-between text-[10px] text-gray-300 mt-0.5">
        <span>{homeLabel}</span><span>{awayLabel}</span>
      </div>
    </div>
  );
}

function EdgeBar({ label, value, leftLabel, rightLabel }: {
  label: string; value: number | null | undefined; leftLabel: string; rightLabel: string;
}) {
  const v = value ?? 0;
  const halfPct = Math.min(50, Math.abs(v) * 60);
  const isHome = v >= 0;
  return (
    <div>
      <div className="flex justify-between text-[10px] text-gray-400 mb-1">
        <span>← {leftLabel} üstün</span>
        <span className="font-medium text-gray-600">{label}</span>
        <span>{rightLabel} üstün →</span>
      </div>
      <div className="relative h-2.5 bg-gray-100 rounded-full overflow-hidden">
        <div className="absolute inset-y-0 left-1/2 w-px bg-gray-300" />
        <div className={`absolute inset-y-0 ${isHome ? "bg-blue-400" : "bg-red-400"} rounded-full`}
          style={isHome ? { left: "50%", width: `${halfPct}%` } : { right: "50%", width: `${halfPct}%` }} />
      </div>
      <p className="text-center text-[10px] text-gray-400 mt-0.5">
        {Math.abs(v) < 0.01 ? "Dengeli" : isHome
          ? `${rightLabel} +${(v * 100).toFixed(0)} puan`
          : `${leftLabel} +${(Math.abs(v) * 100).toFixed(0)} puan`}
      </p>
    </div>
  );
}

// Horizontal win-rate bar for H2H
function H2HRateBar({ homeRate, drawRate, awayRate, homeTeam, awayTeam }: {
  homeRate: number; drawRate: number; awayRate: number; homeTeam: string; awayTeam: string;
}) {
  const h = Math.round(homeRate * 100);
  const d = Math.round(drawRate * 100);
  const a = Math.round(awayRate * 100);
  return (
    <div>
      <div className="flex h-5 rounded overflow-hidden text-white text-[10px] font-bold">
        <div className="bg-blue-500 flex items-center justify-center" style={{ width: `${h}%` }}>{h > 12 && `${h}%`}</div>
        <div className="bg-amber-400 flex items-center justify-center" style={{ width: `${d}%` }}>{d > 8 && `${d}%`}</div>
        <div className="bg-red-500 flex items-center justify-center" style={{ width: `${a}%` }}>{a > 12 && `${a}%`}</div>
      </div>
      <div className="flex justify-between text-[10px] text-gray-400 mt-0.5">
        <span className="text-blue-600 font-medium">{homeTeam}</span>
        <span>Beraberlik</span>
        <span className="text-red-500 font-medium">{awayTeam}</span>
      </div>
    </div>
  );
}

// Motivation bar with sub-label
function MotivationBar({ score, label, color }: { score: number | null; label: string; color: string }) {
  if (score == null) return (
    <div className="flex-1">
      <div className="text-xs text-gray-400 mb-1">{label}</div>
      <div className="h-2 bg-gray-100 rounded" />
      <div className="text-[10px] text-gray-300 mt-0.5">Veri yok</div>
    </div>
  );
  const pct = Math.round(score * 100);
  return (
    <div className="flex-1">
      <div className="flex justify-between text-xs mb-1">
        <span className="text-gray-500">{label}</span>
        <span className={`font-bold ${color}`}>{pct}%</span>
      </div>
      <div className="h-2 bg-gray-100 rounded overflow-hidden">
        <div className={`h-full rounded transition-all ${color === "text-blue-700" ? "bg-blue-500" : "bg-red-500"}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function motivationSublabel(f: MatchFeatures, side: "home" | "away"): string {
  const par = (pts_above_rel: number | null, pts_title: number | null, pts_top4: number | null, pts_top6: number | null) => {
    if (pts_above_rel != null && pts_above_rel <= 3) return `Düşme hattına ${pts_above_rel} puan`;
    if (pts_title != null && pts_title <= 6) return `Şampiyonluğa ${pts_title} puan`;
    if (pts_top4 != null && pts_top4 <= 4) return `4. sıraya ${pts_top4} puan`;
    if (pts_top6 != null && pts_top6 <= 3) return `6. sıraya ${pts_top6} puan`;
    return "Orta sıra";
  };
  if (side === "home") return par(f.points_above_relegation_home, f.points_to_title_home, f.points_to_top4_home, f.points_to_top6_home);
  return par(f.points_above_relegation_away, f.points_to_title_away, f.points_to_top4_away, f.points_to_top6_away);
}

// Sharp money arrow indicator
function SharpMoneyIndicator({ signal }: { signal: number | null }) {
  if (signal == null) return null;
  const abs = Math.abs(signal);
  if (abs < 0.3) return <span className="text-xs text-gray-400">Nötr</span>;
  const toward = signal > 0 ? "Deplasman" : "Ev Sahibi";
  const color = signal > 0 ? "text-red-600" : "text-blue-700";
  const strength = abs > 0.7 ? "Güçlü" : "Orta";
  return (
    <span className={`text-xs font-semibold ${color}`}>
      {strength} → {toward} {signal > 0 ? "→" : "←"}
    </span>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function MatchDetailPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const poolId = searchParams.get("pool");
  const matchId = params.matchId;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [match, setMatch] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!poolId) { setError(true); setLoading(false); return; }
    fetch(`${BASE_URL}/weekly-pools/${poolId}/matches/${matchId}`)
      .then((r) => r.ok ? r.json() : Promise.reject(r))
      .then((d) => { setMatch(d); setLoading(false); })
      .catch(() => { setError(true); setLoading(false); });
  }, [poolId, matchId]);

  if (error) return (
    <div className="text-center py-20 text-red-500">
      <p className="text-lg font-semibold">Maç bulunamadı</p>
      <Link href="/" className="text-sm text-blue-500 hover:underline mt-2 block">← Tabloya dön</Link>
    </div>
  );

  if (loading) return (
    <div className="max-w-3xl mx-auto space-y-4">
      <div className="h-4 w-24 bg-gray-200 rounded animate-pulse" />
      <SkeletonCard /><SkeletonCard /><SkeletonCard />
    </div>
  );

  const score = match.latest_score;
  const feats: MatchFeatures | null = match.features;
  const homeTeam: string = match.home_team;
  const awayTeam: string = match.away_team;
  const h2h: unknown[] = match.h2h ?? [];
  const history: unknown[] = match.score_history ?? [];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const homeTeamForm: any = match.home_team_form ?? null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const awayTeamForm: any = match.away_team_form ?? null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const homeAbsences: any[] = match.home_absences ?? [];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const awayAbsences: any[] = match.away_absences ?? [];

  const cov = score?.recommended_coverage ?? score?.primary_pick ?? "?";
  const badgeCls = BADGE[cov] ?? "bg-gray-100 text-gray-700";
  const exp = buildExplanation(feats, score, homeTeam, awayTeam);

  // Derived flags
  const isDerby = feats?.is_derby || false;
  const hasContext = feats && (feats.rest_days_home_actual != null || feats.post_intl_break_home != null);
  const hasMotivation = feats && (feats.motivation_home != null || feats.motivation_away != null);
  const hasOddsMovement = feats && feats.opening_odds_home != null;
  const hasXG = feats && feats.xg_proxy_home != null;
  const hasH2HStats = feats && feats.h2h_sample_size != null && (feats.h2h_sample_size ?? 0) > 0;

  // Opening vs current odds for movement
  const openingOdds = feats ? { home: feats.opening_odds_home, draw: feats.opening_odds_draw, away: feats.opening_odds_away } : null;
  const currentOdds = feats?.odds ?? null;

  // Radar: 8 dimensions (added Motivasyon + Dep. Form)
  const radarDims = feats ? [
    { label: "Güç",        home: feats.home?.strength_score ?? 0.5,  away: feats.away?.strength_score ?? 0.5 },
    { label: "Form",       home: feats.home?.form_score ?? 0.5,       away: feats.away?.form_score ?? 0.5 },
    { label: "Hücum",      home: feats.home?.attack_index ?? 0.5,     away: feats.away?.attack_index ?? 0.5 },
    { label: "Savunma",    home: feats.home?.defense_index ?? 0.5,    away: feats.away?.defense_index ?? 0.5 },
    { label: "Motivasyon", home: feats.motivation_home ?? 0.3,        away: feats.motivation_away ?? 0.3 },
    { label: "Dep. Form",  home: feats.away_form_home ?? 0.4,         away: feats.away_form_away ?? 0.4 },
    { label: "Bera. Riski",home: feats.draw_tendency ?? 0.5,          away: feats.draw_tendency ?? 0.5 },
    { label: "Piyasa",     home: feats.market_support ?? 0.33,        away: 1 - (feats.market_support ?? 0.33) },
  ] : [];

  return (
    <div className="max-w-3xl mx-auto space-y-4">
      <Link href="/" className="text-sm text-blue-600 hover:underline block">← Haftalık Tablo</Link>

      {/* ── Derby alert ──────────────────────────────────────────────────────── */}
      {isDerby && (
        <div className="bg-orange-50 border border-orange-200 rounded-xl p-4 flex gap-3 items-start">
          <span className="text-2xl shrink-0">🔥</span>
          <div>
            <p className="font-bold text-orange-800 text-sm">Derby Maçı</p>
            <p className="text-xs text-orange-600 mt-0.5">
              Bu maç tarihi bir rekabet olarak işaretlendi. Derby maçlarında model güven skoru %25 baskılanır — sürpriz olasılığı yüksektir.
            </p>
          </div>
        </div>
      )}

      {/* ── Header card ──────────────────────────────────────────────────────── */}
      <div className="bg-white rounded-xl shadow p-5">
        <div className="flex items-center justify-between mb-1 flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono text-gray-400">Maç {match.sequence_no}</span>
            {isDerby && <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-orange-100 text-orange-700 border border-orange-200">DERBY</span>}
          </div>
          <span className={`text-xs px-2 py-0.5 rounded font-medium ${match.is_locked ? "bg-gray-100 text-gray-500" : "bg-green-100 text-green-700"}`}>
            {match.is_locked ? `Kilitli · ${match.result ?? ""}` : "Açık"}
          </span>
        </div>
        {match.kickoff_at && (
          <p className="text-xs text-gray-400 mb-3">
            {new Date(match.kickoff_at).toLocaleString("tr-TR", { weekday: "long", day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" })}
          </p>
        )}

        <div className="grid grid-cols-3 items-center gap-2 mb-5">
          <div className="text-center">
            <p className="text-lg sm:text-xl font-extrabold text-gray-900 leading-tight">{homeTeam}</p>
            <p className="text-xs text-blue-500 mt-0.5">Ev Sahibi</p>
          </div>
          <div className="text-center text-2xl font-thin text-gray-200">VS</div>
          <div className="text-center">
            <p className="text-lg sm:text-xl font-extrabold text-gray-900 leading-tight">{awayTeam}</p>
            <p className="text-xs text-red-400 mt-0.5">Deplasman</p>
          </div>
        </div>

        {score ? (
          <>
            <ProbBar p1={score.p1} px={score.px} p2={score.p2} primary={score.primary_pick} />
            <div className="mt-4 flex flex-wrap items-center gap-4">
              <div className="flex items-center gap-2">
                <ConfidenceRing score={score.confidence_score} pick={score.primary_pick} size={52} />
                <div>
                  <p className="text-xs text-gray-400">Güven{isDerby && <span className="ml-1 text-orange-500 text-[10px]">×0.75 derby</span>}</p>
                  <p className={`text-xl font-black ${(score.confidence_score ?? 0) >= 55 ? "text-green-600" : (score.confidence_score ?? 0) >= 30 ? "text-amber-600" : "text-red-500"}`}>
                    %{(score.confidence_score ?? 0).toFixed(0)}
                  </p>
                </div>
              </div>
              <div>
                <p className="text-xs text-gray-400 mb-1">Öneri</p>
                <span className={`text-sm font-bold px-3 py-1 rounded-full border ${badgeCls}`}>
                  {cov} {cov === "1X2" ? "(Üçlü)" : cov.length === 2 ? "(İkili)" : "(Tekli)"}
                </span>
              </div>
              <div>
                <p className="text-xs text-gray-400">Kapsam İhtiyacı</p>
                <div className="flex items-center gap-1.5">
                  <p className="text-lg font-bold text-gray-700">{score.coverage_need_score?.toFixed(0) ?? "—"}</p>
                  <span className="text-xs text-gray-400">/100</span>
                </div>
              </div>
            </div>
            {score.reason_codes?.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {score.reason_codes.map((code: string) => (
                  <span key={code} className="bg-blue-50 text-blue-700 text-xs px-2.5 py-0.5 rounded-full border border-blue-100">
                    {REASON_LABEL[code] ?? code}
                  </span>
                ))}
              </div>
            )}
          </>
        ) : (
          <p className="text-center text-gray-400 text-sm py-4">Skor henüz hesaplanmadı.</p>
        )}
      </div>

      {/* ── Last 5 league form + season record ───────────────────────────────── */}
      {(homeTeamForm || awayTeamForm) && (
        <div className="bg-white rounded-xl shadow p-5">
          <h2 className="text-sm font-bold text-gray-700 mb-4">Lig Formu (Son 5 Maç)</h2>
          <div className="grid grid-cols-2 gap-5">
            {([
              { team: homeTeam, form: homeTeamForm, sideColor: "text-blue-600", recKey: "home_record", recLabel: "Evde" },
              { team: awayTeam, form: awayTeamForm, sideColor: "text-red-500", recKey: "away_record", recLabel: "Deplasmanda" },
            ] as const).map(({ team, form, sideColor, recKey, recLabel }) => {
              if (!form) return (
                <div key={team}>
                  <p className={`text-xs font-semibold mb-2 truncate ${sideColor}`}>{team}</p>
                  <p className="text-xs text-gray-400">Veri yok</p>
                </div>
              );
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              const items: any[] = form.form_items ?? [];
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              const rec: any = (form as any)[recKey] ?? {};
              const FORM_PILL: Record<string, string> = {
                W: "bg-green-500 text-white", D: "bg-amber-400 text-white", L: "bg-red-500 text-white", "?": "bg-gray-200 text-gray-500",
              };
              return (
                <div key={team}>
                  <div className="flex items-center justify-between mb-2">
                    <p className={`text-xs font-semibold truncate ${sideColor}`}>{team}</p>
                    {form.rank && <span className="text-[10px] text-gray-400 shrink-0 ml-1">{form.rank}. sıra · {form.points} puan</span>}
                  </div>
                  {/* Form pills — most recent last in API, reverse to show most recent first */}
                  <div className="flex gap-1 mb-3">
                    {[...items].reverse().map((item, i) => (
                      <span key={i} className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0 ${FORM_PILL[item.result] ?? FORM_PILL["?"]}`}>
                        {item.label}
                      </span>
                    ))}
                    {items.length === 0 && <span className="text-xs text-gray-400">—</span>}
                  </div>
                  {/* Venue-specific record */}
                  {rec.played > 0 && (
                    <div className="text-[10px] text-gray-500">
                      <span className="font-semibold text-gray-700">{recLabel}: </span>
                      <span className="text-green-600 font-semibold">{rec.win}G</span>
                      {" "}<span className="text-amber-500 font-semibold">{rec.draw}B</span>
                      {" "}<span className="text-red-500 font-semibold">{rec.lose}M</span>
                      {" "}·{" "}
                      <span className="text-gray-600">{rec.goals_for} atılan / {rec.goals_against} yenilen ({rec.played} maç)</span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Context strip: rest days / break / congestion ─────────────────────── */}
      {hasContext && (
        <div className="bg-white rounded-xl shadow p-4">
          <h2 className="text-sm font-bold text-gray-700 mb-3">Program & Bağlam</h2>
          <div className="grid grid-cols-2 gap-3">
            {/* Rest days */}
            <div>
              <p className="text-[10px] text-gray-400 uppercase tracking-wide mb-2">Dinlenme Süresi</p>
              <div className="space-y-2">
                {(["home", "away"] as const).map(side => {
                  const days = side === "home" ? feats?.rest_days_home_actual : feats?.rest_days_away_actual;
                  const team = side === "home" ? homeTeam : awayTeam;
                  const color = days == null ? "bg-gray-200" : days < 4 ? "bg-red-400" : days < 7 ? "bg-amber-400" : "bg-green-400";
                  return (
                    <div key={side} className="flex items-center gap-2">
                      <span className={`text-[10px] font-bold px-1.5 rounded ${side === "home" ? "text-blue-600 bg-blue-50" : "text-red-500 bg-red-50"}`}>{team.slice(0, 8)}</span>
                      <div className="flex-1 h-2 bg-gray-100 rounded overflow-hidden">
                        <div className={`h-full ${color}`} style={{ width: `${Math.min(100, ((days ?? 7) / 14) * 100)}%` }} />
                      </div>
                      <span className="text-xs font-mono text-gray-600 w-12 text-right">{days != null ? `${Math.round(days)} gün` : "—"}</span>
                    </div>
                  );
                })}
              </div>
            </div>
            {/* Badges */}
            <div>
              <p className="text-[10px] text-gray-400 uppercase tracking-wide mb-2">Uyarılar</p>
              <div className="flex flex-wrap gap-1.5">
                {feats?.post_intl_break_home && (
                  <span className="text-xs px-2 py-1 rounded-full bg-blue-50 text-blue-700 border border-blue-200 font-medium">🌍 {homeTeam.slice(0,8)} milli arada</span>
                )}
                {feats?.post_intl_break_away && (
                  <span className="text-xs px-2 py-1 rounded-full bg-blue-50 text-blue-700 border border-blue-200 font-medium">🌍 {awayTeam.slice(0,8)} milli arada</span>
                )}
                {feats?.congestion_risk_home && (
                  <span className="text-xs px-2 py-1 rounded-full bg-amber-50 text-amber-700 border border-amber-200 font-medium">📅 {homeTeam.slice(0,8)} yoğun program</span>
                )}
                {feats?.congestion_risk_away && (
                  <span className="text-xs px-2 py-1 rounded-full bg-amber-50 text-amber-700 border border-amber-200 font-medium">📅 {awayTeam.slice(0,8)} yoğun program</span>
                )}
                {feats?.long_unbeaten_home && (
                  <span className="text-xs px-2 py-1 rounded-full bg-purple-50 text-purple-700 border border-purple-200 font-medium">🏆 {homeTeam.slice(0,8)} uzun seri</span>
                )}
                {feats?.long_unbeaten_away && (
                  <span className="text-xs px-2 py-1 rounded-full bg-purple-50 text-purple-700 border border-purple-200 font-medium">🏆 {awayTeam.slice(0,8)} uzun seri</span>
                )}
                {!feats?.post_intl_break_home && !feats?.post_intl_break_away && !feats?.congestion_risk_home && !feats?.congestion_risk_away && !feats?.long_unbeaten_home && !feats?.long_unbeaten_away && (
                  <span className="text-xs text-gray-400">Program uyarısı yok</span>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Motivation bars ───────────────────────────────────────────────────── */}
      {hasMotivation && (
        <div className="bg-white rounded-xl shadow p-5">
          <h2 className="text-sm font-bold text-gray-700 mb-4">Motivasyon & Hedef</h2>
          <div className="flex gap-6">
            <MotivationBar score={feats!.motivation_home} label={homeTeam} color="text-blue-700" />
            <MotivationBar score={feats!.motivation_away} label={awayTeam} color="text-red-600" />
          </div>
          <div className="mt-3 flex justify-between text-xs text-gray-500">
            <span className="text-blue-600">{feats && motivationSublabel(feats, "home")}</span>
            <span className="text-red-500">{feats && motivationSublabel(feats, "away")}</span>
          </div>
        </div>
      )}

      {/* ── Why this recommendation ───────────────────────────────────────────── */}
      {score && (
        <div className="bg-white rounded-xl shadow p-5">
          <h2 className="text-sm font-bold text-gray-700 mb-3">Neden Bu Öneri?</h2>
          <div className="space-y-3">
            {[
              { icon: "🎯", label: "Birincil Sinyal", text: exp.primary_reason },
              { icon: "⚠️", label: "Risk Faktörü", text: exp.risk_factor },
              { icon: "🛡️", label: "Kapsam Gerekçesi", text: exp.coverage_rationale },
            ].map(({ icon, label, text }) => (
              <div key={label} className="flex gap-3 items-start">
                <span className="text-lg shrink-0">{icon}</span>
                <div>
                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-0.5">{label}</p>
                  <p className="text-sm text-gray-800">{text}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Odds movement ─────────────────────────────────────────────────────── */}
      {hasOddsMovement ? (
        <SubscriberGate fallback={<BlurPlaceholder section="odds" />}>
          <div className="bg-white rounded-xl shadow p-5">
            <h2 className="text-sm font-bold text-gray-700 mb-3">Oran Hareketi & Sharp Money</h2>
            <div className="grid grid-cols-3 gap-3 mb-4">
              {(["1", "X", "2"] as const).map((label) => {
                const openVal = label === "1" ? openingOdds?.home : label === "X" ? openingOdds?.draw : openingOdds?.away;
                const currVal = label === "1" ? currentOdds?.home : label === "X" ? currentOdds?.draw : currentOdds?.away;
                const delta = openVal != null && currVal != null ? currVal - openVal : null;
                const deltaColor = delta == null ? "" : delta > 0.05 ? "text-red-500" : delta < -0.05 ? "text-green-600" : "text-gray-500";
                return (
                  <div key={label} className={`border rounded-lg p-3 text-center ${BADGE[label]}`}>
                    <p className="text-sm font-bold">{label}</p>
                    <p className="text-xs text-current opacity-60 mt-0.5">Açılış</p>
                    <p className="text-lg font-extrabold">{openVal != null ? openVal.toFixed(2) : "—"}</p>
                    {delta != null && (
                      <p className={`text-xs font-semibold mt-1 ${deltaColor}`}>
                        {delta > 0 ? "+" : ""}{delta.toFixed(2)} {delta > 0.05 ? "↑" : delta < -0.05 ? "↓" : "~"}
                      </p>
                    )}
                    {currVal != null && <p className="text-[10px] opacity-50 mt-0.5">Güncel: {currVal.toFixed(2)}</p>}
                  </div>
                );
              })}
            </div>
            <div className="bg-gray-50 rounded-lg p-3 flex items-center justify-between">
              <div>
                <p className="text-xs font-semibold text-gray-600 mb-0.5">Sharp Money Sinyali</p>
                <SharpMoneyIndicator signal={feats?.sharp_money_signal ?? null} />
              </div>
              <div className="text-right">
                <div className="w-24 h-2 bg-gray-200 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full ${(feats?.sharp_money_signal ?? 0) > 0 ? "bg-red-500 ml-auto" : "bg-blue-500"}`}
                    style={{ width: `${Math.abs(feats?.sharp_money_signal ?? 0) * 100}%`, marginLeft: (feats?.sharp_money_signal ?? 0) > 0 ? "auto" : 0 }}
                  />
                </div>
                <p className="text-[10px] text-gray-400 mt-0.5">← Ev · Dep →</p>
              </div>
            </div>
          </div>
        </SubscriberGate>
      ) : (feats?.odds && (feats.odds.home || feats.odds.draw || feats.odds.away)) ? (
        <div className="bg-white rounded-xl shadow p-5">
          <h2 className="text-sm font-bold text-gray-700 mb-3">Bahis Oranları</h2>
          <div className="grid grid-cols-3 gap-3 text-center">
            {(["1", "X", "2"] as const).map((label) => {
              const val = label === "1" ? feats.odds?.home : label === "X" ? feats.odds?.draw : feats.odds?.away;
              return (
                <div key={label} className={`border rounded-lg p-3 ${BADGE[label]}`}>
                  <p className="text-lg font-bold">{label}</p>
                  <p className="text-2xl font-extrabold mt-1">{val != null ? val.toFixed(2) : "—"}</p>
                  {val != null && <p className="text-xs opacity-60 mt-0.5">imp. {(1 / val * 100).toFixed(0)}%</p>}
                </div>
              );
            })}
          </div>
          <p className="text-xs text-gray-400 mt-2 text-center">Kaynak: Bet365 · Tarihsel snapshot</p>
        </div>
      ) : (
        <div className="bg-white rounded-xl shadow p-5">
          <h2 className="text-sm font-bold text-gray-700 mb-1">Bahis Oranları</h2>
          <p className="text-xs text-gray-400">Oranlar mevcut değil — tarihsel maç veya veri henüz çekilmedi.</p>
        </div>
      )}

      {/* ── xG & luck section ─────────────────────────────────────────────────── */}
      {hasXG && (
        <div className="bg-white rounded-xl shadow p-5">
          <h2 className="text-sm font-bold text-gray-700 mb-3">xG Proxy & Form Kalitesi</h2>
          <div className="space-y-3">
            {/* xG bar comparison */}
            <div>
              <p className="text-xs text-gray-400 mb-2">xG proxy (son 5 maç ort., son 5 maç şut × 0.33)</p>
              {(["home", "away"] as const).map(side => {
                const xg = side === "home" ? feats?.xg_proxy_home : feats?.xg_proxy_away;
                const luck = side === "home" ? feats?.xg_luck_home : feats?.xg_luck_away;
                const team = side === "home" ? homeTeam : awayTeam;
                const color = side === "home" ? "bg-blue-400" : "bg-red-400";
                const textColor = side === "home" ? "text-blue-600" : "text-red-500";
                return (
                  <div key={side} className="flex items-center gap-2 mb-1">
                    <span className={`text-[10px] font-bold px-1 rounded w-20 shrink-0 ${textColor}`}>{team.slice(0, 10)}</span>
                    <div className="flex-1 h-3 bg-gray-100 rounded overflow-hidden">
                      <div className={`h-full ${color} rounded`} style={{ width: `${Math.min(100, (xg ?? 0) * 50)}%` }} />
                    </div>
                    <span className="text-xs font-mono text-gray-600 w-10 text-right">{xg?.toFixed(2) ?? "—"}</span>
                    {luck != null && (
                      <span className={`text-[10px] font-medium w-16 text-right ${luck > 0.4 ? "text-amber-500" : luck < -0.4 ? "text-blue-600" : "text-gray-400"}`}>
                        {luck > 0.4 ? "🍀 şanslı" : luck < -0.4 ? "😓 şanssız" : "dengeli"}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
            {/* Lucky/unlucky flags */}
            <div className="flex flex-wrap gap-2 pt-1 border-t border-gray-50">
              {feats?.lucky_form_home && <span className="text-xs px-2 py-1 rounded-full bg-amber-50 text-amber-700 border border-amber-200">🍀 {homeTeam.slice(0,8)} şanslı form (ortalamadan yüksek gol)</span>}
              {feats?.lucky_form_away && <span className="text-xs px-2 py-1 rounded-full bg-amber-50 text-amber-700 border border-amber-200">🍀 {awayTeam.slice(0,8)} şanslı form</span>}
              {feats?.unlucky_form_home && <span className="text-xs px-2 py-1 rounded-full bg-blue-50 text-blue-700 border border-blue-200">😓 {homeTeam.slice(0,8)} şanssız form (ortalamadan düşük gol)</span>}
              {feats?.unlucky_form_away && <span className="text-xs px-2 py-1 rounded-full bg-blue-50 text-blue-700 border border-blue-200">😓 {awayTeam.slice(0,8)} şanssız form</span>}
              {!feats?.lucky_form_home && !feats?.lucky_form_away && !feats?.unlucky_form_home && !feats?.unlucky_form_away && (
                <span className="text-xs text-gray-400">Şans düzeltmesi yok — form kalitesi dengeli</span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Radar + Team comparison ───────────────────────────────────────────── */}
      {feats?.home && feats?.away ? (
        <SubscriberGate fallback={<BlurPlaceholder section="radar" />}>
          <div className="bg-white rounded-xl shadow p-5">
            <h2 className="text-sm font-bold text-gray-700 mb-4">Takım Karşılaştırması</h2>
            <div className="flex flex-col sm:flex-row gap-4 items-center">
              <div className="flex-1">
                <RadarChart dimensions={radarDims} homeTeam={homeTeam} awayTeam={awayTeam} size={240} />
              </div>
              <div className="flex-1 w-full space-y-1">
                <StatRow label="Güç Skoru" homeVal={feats.home.strength_score} awayVal={feats.away.strength_score}
                  homeLabel={homeTeam} awayLabel={awayTeam} fmt={(v) => (v * 100).toFixed(0)} />
                <StatRow label="Form Skoru" homeVal={feats.home.form_score} awayVal={feats.away.form_score}
                  homeLabel={homeTeam} awayLabel={awayTeam} fmt={(v) => (v * 100).toFixed(0)} />
                <StatRow label="Motivasyon" homeVal={feats.motivation_home} awayVal={feats.motivation_away}
                  homeLabel={homeTeam} awayLabel={awayTeam} fmt={(v) => (v * 100).toFixed(0)} />
                <StatRow label="Dep. Form" homeVal={feats.away_form_home} awayVal={feats.away_form_away}
                  homeLabel={homeTeam} awayLabel={awayTeam} fmt={(v) => (v * 100).toFixed(0)} />
                <StatRow label="Maç Başı Puan" homeVal={feats.home.season_ppg} awayVal={feats.away.season_ppg}
                  homeLabel={homeTeam} awayLabel={awayTeam} fmt={(v) => v.toFixed(2)} />
                <StatRow label="Gol Farkı / Maç" homeVal={feats.home.goal_diff_per_game} awayVal={feats.away.goal_diff_per_game}
                  homeLabel={homeTeam} awayLabel={awayTeam} fmt={(v) => (v > 0 ? "+" : "") + v.toFixed(2)} />
                <StatRow label="Hücum Gücü" homeVal={feats.home.attack_index} awayVal={feats.away.attack_index}
                  homeLabel={homeTeam} awayLabel={awayTeam} fmt={(v) => (v * 100).toFixed(0)} />
                <StatRow label="Savunma Gücü" homeVal={feats.home.defense_index} awayVal={feats.away.defense_index}
                  homeLabel={homeTeam} awayLabel={awayTeam} fmt={(v) => (v * 100).toFixed(0)} />
              </div>
            </div>
            <div className="mt-5 space-y-3 border-t pt-4">
              <EdgeBar label="Güç Farkı" value={feats.strength_edge} leftLabel={awayTeam} rightLabel={homeTeam} />
              <EdgeBar label="Form Farkı" value={feats.form_edge} leftLabel={awayTeam} rightLabel={homeTeam} />
            </div>
          </div>
        </SubscriberGate>
      ) : (
        <div className="bg-white rounded-xl shadow p-5">
          <h2 className="text-sm font-bold text-gray-700 mb-1">Takım Karşılaştırması</h2>
          <SkeletonBlock lines={4} />
          <p className="text-xs text-amber-500 mt-2">Özellik verisi bekleniyor</p>
        </div>
      )}

      {/* ── Key absences — penalty score + player names ───────────────────────── */}
      {(homeAbsences.length > 0 || awayAbsences.length > 0 || (feats && (
        (feats.lineup_penalty_home ?? 0) > 0.05 ||
        (feats.lineup_penalty_away ?? 0) > 0.05 ||
        feats.key_attacker_absent_home ||
        feats.key_attacker_absent_away ||
        feats.key_defender_absent_home ||
        feats.key_defender_absent_away
      ))) ? (
        <div className="bg-white rounded-xl shadow p-5 border-l-4 border-l-amber-400">
          <h2 className="text-sm font-bold text-gray-700 mb-3">⚠ Kadro Uyarısı</h2>
          <div className="grid grid-cols-2 gap-4">
            {[
              {
                team: homeTeam,
                penalty: feats?.lineup_penalty_home,
                attacker: feats?.key_attacker_absent_home,
                defender: feats?.key_defender_absent_home,
                color: "text-blue-700",
                absences: homeAbsences,
              },
              {
                team: awayTeam,
                penalty: feats?.lineup_penalty_away,
                attacker: feats?.key_attacker_absent_away,
                defender: feats?.key_defender_absent_away,
                color: "text-red-600",
                absences: awayAbsences,
              },
            ].map(({ team, penalty, attacker, defender, color, absences }) => (
              <div key={team}>
                <p className={`font-semibold text-sm ${color} mb-1`}>{team}</p>
                {(penalty ?? 0) > 0.05 && (
                  <p className="text-xs text-gray-500 mb-1">
                    Kadro etkisi: <span className="font-bold text-red-500">{((penalty ?? 0) * 100).toFixed(0)}/100</span>
                  </p>
                )}
                {/* Broad absence-type badges */}
                <div className="flex flex-wrap gap-1 mb-2">
                  {attacker && <span className="text-[10px] px-2 py-0.5 rounded-full bg-red-50 text-red-700 border border-red-200 font-medium">⚽ Anahtar Forvet</span>}
                  {defender && <span className="text-[10px] px-2 py-0.5 rounded-full bg-orange-50 text-orange-700 border border-orange-200 font-medium">🛡 Anahtar Defans</span>}
                </div>
                {/* Player list */}
                {absences.length > 0 ? (
                  <ul className="space-y-1">
                    {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                    {absences.map((p: any, i: number) => {
                      const isConfirmed = p.is_confirmed;
                      const typeLabel = p.absence_type === "Missing Fixture" ? "Cezalı" : p.absence_type === "Injured" ? "Sakatlanmış" : "Şüpheli";
                      const dotColor = isConfirmed ? "bg-red-500" : "bg-amber-400";
                      return (
                        <li key={i} className="flex items-start gap-2 text-xs">
                          <span className={`mt-1 w-1.5 h-1.5 rounded-full shrink-0 ${dotColor}`} />
                          <span>
                            <span className="font-semibold text-gray-800">{p.name}</span>
                            <span className={`ml-1 text-[10px] font-medium ${isConfirmed ? "text-red-600" : "text-amber-600"}`}>
                              {typeLabel}
                            </span>
                            {p.reason && (
                              <span className="ml-1 text-gray-400 text-[10px]">({p.reason})</span>
                            )}
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                ) : (penalty ?? 0) > 0.05 ? (
                  <p className="text-[10px] text-gray-400">Genel kadro eksikliği</p>
                ) : (
                  <p className="text-[10px] text-green-600">Eksik yok</p>
                )}
              </div>
            ))}
          </div>
        </div>
      ) : feats && (feats.lineup_certainty ?? 1) < 0.3 ? (
        <div className="bg-gray-50 rounded-xl shadow p-4">
          <p className="text-xs text-gray-500">⏳ <strong>Kadro bilgisi henüz gelmedi</strong> — ilk 11 genellikle maçtan 2 saat önce açıklanır.</p>
        </div>
      ) : null}

      {/* ── Feature gauges ────────────────────────────────────────────────────── */}
      {feats ? (
        <div className="bg-white rounded-xl shadow p-5">
          <h2 className="text-sm font-bold text-gray-700 mb-3">Maç Analizi</h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            <Gauge label="Beraberlik Eğilimi" value={feats.draw_tendency} description="0=kesin sonuç · 100=yüksek bera. riski" />
            <Gauge label="Denge Skoru" value={feats.balance_score} description="İki takımın ne kadar dengeli olduğu" />
            <Gauge label="Düşük Tempo" value={feats.low_tempo_signal} description="Az şut / az atak beklentisi" />
            <Gauge label="Az Gol (u2.5)" value={feats.low_goal_signal} description="2.5 altı gol olasılığı" />
            <Gauge label="Beraberlik Tarihi" value={feats.draw_history} description="Bu iki takım arasındaki geçmiş bera. oranı" />
            <Gauge label="Taktik Simetri" value={feats.tactical_symmetry} description="Benzer oyun stili / taktik profil" />
            <Gauge label="Piyasa Desteği" value={feats.market_support} description="Piyasanın ev sahibine verdiği ağırlık" />
            <Gauge label="Volatilite" value={feats.volatility_score} description="Tahmin güçlüğü — sürpriz riski" />
            <Gauge label="Diziliş Güveni" value={feats.lineup_certainty} description="İlk 11 bilgisinin güvenilirliği" />
          </div>
        </div>
      ) : null}

      {/* ── H2H (upgraded: win-rate bars + bogey flag) ───────────────────────── */}
      <div className="bg-white rounded-xl shadow p-5">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <h2 className="text-sm font-bold text-gray-700">Son Karşılaşmalar (H2H)</h2>
          {feats?.h2h_bogey_flag && (
            <span className="text-xs px-2 py-1 rounded-full bg-red-50 text-red-700 border border-red-200 font-semibold">
              ⚠ Bogey Takım — {awayTeam} tarihsel üstünlüğü var
            </span>
          )}
        </div>

        {hasH2HStats && (
          <div className="mb-4">
            <H2HRateBar
              homeRate={feats!.h2h_home_win_rate ?? 0.33}
              drawRate={feats!.h2h_draw_rate ?? 0.33}
              awayRate={feats!.h2h_away_win_rate ?? 0.33}
              homeTeam={homeTeam}
              awayTeam={awayTeam}
            />
            {feats?.h2h_venue_home_win_rate != null && (
              <p className="text-[10px] text-gray-400 mt-1 text-center">
                Bu stadyumda ev galibiyeti: <strong>{Math.round((feats.h2h_venue_home_win_rate ?? 0) * 100)}%</strong> · {feats.h2h_sample_size} maç
              </p>
            )}
          </div>
        )}

        {h2h.length === 0 ? (
          <p className="text-xs text-gray-400">Bu iki takım arasında veritabanında kayıtlı karşılaşma bulunmuyor.</p>
        ) : (
          <div className="space-y-2">
            {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
            {(h2h as any[]).map((g: any, i: number) => {
              const res: string = g.result_from_home_perspective ?? "?";
              const pillCls = H2H_PILL[res] ?? H2H_PILL["?"];
              return (
                <div key={i} className="flex items-center gap-3 text-sm">
                  <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${pillCls}`}>{res}</span>
                  <span className="flex-1 text-gray-700">{g.home_team} <span className="font-bold">{g.home_score ?? "?"} – {g.away_score ?? "?"}</span> {g.away_team}</span>
                  <span className="text-xs text-gray-400 shrink-0">
                    {g.kickoff_at ? new Date(g.kickoff_at).toLocaleDateString("tr-TR", { day: "numeric", month: "short", year: "numeric" }) : ""}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* ── Score history ─────────────────────────────────────────────────────── */}
      {history.length > 0 && (
        <SubscriberGate fallback={<BlurPlaceholder section="history" />}>
          <div className="bg-white rounded-xl shadow p-5">
            <h2 className="text-sm font-bold text-gray-700 mb-3">Skor Değişim Geçmişi</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-xs min-w-[480px]">
                <thead>
                  <tr className="text-gray-400 border-b">
                    <th className="text-left pb-2 font-medium">Tarih / Saat</th>
                    <th className="text-center pb-2 font-medium text-blue-500">1</th>
                    <th className="text-center pb-2 font-medium text-amber-500">X</th>
                    <th className="text-center pb-2 font-medium text-red-500">2</th>
                    <th className="text-center pb-2 font-medium">Birincil</th>
                    <th className="text-center pb-2 font-medium">Öneri</th>
                    <th className="text-center pb-2 font-medium">Güven</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                  {(history as any[]).map((h: any, i: number) => {
                    const prevPick = (history as any[])[i + 1]?.primary_pick;
                    const changed = prevPick && prevPick !== h.primary_pick;
                    return (
                      <tr key={i} className={`${i === 0 ? "font-semibold" : "text-gray-500"} ${changed ? "bg-amber-50" : ""}`}>
                        <td className="py-1.5">
                          {new Date(h.created_at).toLocaleString("tr-TR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                          {changed && <span className="ml-1 text-amber-500 text-[10px]">↺ değişti</span>}
                        </td>
                        <td className="text-center text-blue-500">{(h.p1 * 100).toFixed(0)}%</td>
                        <td className="text-center text-amber-500">{(h.px * 100).toFixed(0)}%</td>
                        <td className="text-center text-red-500">{(h.p2 * 100).toFixed(0)}%</td>
                        <td className="text-center font-bold">{h.primary_pick}</td>
                        <td className="text-center">{h.coverage_pick ?? "—"}</td>
                        <td className="text-center">{h.confidence_score != null ? `%${h.confidence_score.toFixed(0)}` : "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </SubscriberGate>
      )}
    </div>
  );
}
