"use client";

import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";
import dynamic from "next/dynamic";
import { buildExplanation, safeVal, fmt } from "@/lib/explanation";
import { SkeletonCard, SkeletonBlock } from "@/components/Skeleton";
import ConfidenceRing from "@/components/ConfidenceRing";
import { SubscriberGate } from "@/components/SubscriberGate";

const RadarChart = dynamic(() => import("@/components/RadarChart"), { ssr: false });

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Helpers ────────────────────────────────────────────────────────────────────

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
          {hv != null && (
            <div className={`h-1.5 rounded-full ${homeWins === true ? "bg-blue-400" : "bg-gray-200"}`}
              style={{ width: `${(hv / max) * 100}%` }} />
          )}
        </div>
        <div className="w-1" />
        <div className="flex-1">
          {av != null && (
            <div className={`h-1.5 rounded-full ${homeWins === false ? "bg-red-400" : "bg-gray-200"}`}
              style={{ width: `${(av / max) * 100}%` }} />
          )}
        </div>
      </div>
      <div className="flex justify-between text-[10px] text-gray-300 mt-0.5">
        <span>{homeLabel}</span>
        <span>{awayLabel}</span>
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
        <div
          className={`absolute inset-y-0 ${isHome ? "bg-blue-400" : "bg-red-400"} rounded-full`}
          style={isHome
            ? { left: "50%", width: `${halfPct}%` }
            : { right: "50%", width: `${halfPct}%` }}
        />
      </div>
      <p className="text-center text-[10px] text-gray-400 mt-0.5">
        {Math.abs(v) < 0.01
          ? "Dengeli"
          : isHome
          ? `${rightLabel} +${(v * 100).toFixed(0)} puan`
          : `${leftLabel} +${(Math.abs(v) * 100).toFixed(0)} puan`}
      </p>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function MatchDetailPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const poolId = searchParams.get("pool");
  const matchId = params.matchId;

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
      <SkeletonCard />
      <SkeletonCard />
      <SkeletonCard />
    </div>
  );

  const score = match.latest_score;
  const feats = match.features;
  const homeTeam: string = match.home_team;
  const awayTeam: string = match.away_team;
  const h2h: any[] = match.h2h ?? [];
  const history: any[] = match.score_history ?? [];

  const cov = score?.recommended_coverage ?? score?.primary_pick ?? "?";
  const badgeCls = BADGE[cov] ?? "bg-gray-100 text-gray-700";
  const exp = buildExplanation(feats, score, homeTeam, awayTeam);

  // Radar dimensions
  const radarDims = feats ? [
    { label: "Güç", home: feats.home?.strength_score ?? 0.5, away: feats.away?.strength_score ?? 0.5 },
    { label: "Form", home: feats.home?.form_score ?? 0.5, away: feats.away?.form_score ?? 0.5 },
    { label: "Hücum", home: feats.home?.attack_index ?? 0.5, away: feats.away?.attack_index ?? 0.5 },
    { label: "Savunma", home: feats.home?.defense_index ?? 0.5, away: feats.away?.defense_index ?? 0.5 },
    { label: "Bera. Riski", home: feats.draw_tendency ?? 0.5, away: feats.draw_tendency ?? 0.5 },
    { label: "Piyasa", home: feats.market_support ?? 0.33, away: feats.market?.implied_p2 ?? 0.33 },
  ] : [];

  return (
    <div className="max-w-3xl mx-auto space-y-4">
      <Link href="/" className="text-sm text-blue-600 hover:underline block">← Haftalık Tablo</Link>

      {/* ── Header card ─────────────────────────────────────────────────────── */}
      <div className="bg-white rounded-xl shadow p-5">
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs font-mono text-gray-400">Maç {match.sequence_no}</span>
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
                  <p className="text-xs text-gray-400">Güven</p>
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
                    {code === "HOME_STRENGTH" ? "Ev güçlü" : code === "AWAY_STRENGTH" ? "Dep. güçlü" : code === "HOME_FORM" ? "Ev formda" : code === "AWAY_FORM" ? "Dep. formda" : code === "DRAW_RISK" ? "Beraberlik riski" : code === "HOME_ABSENCE" ? "Ev eksik" : code === "AWAY_ABSENCE" ? "Dep. eksik" : code === "MARKET_ALIGNED" ? "Piyasa uyumlu" : code === "HIGH_VOLATILITY" ? "Yüksek volatilite" : code === "TRIPLE_RISK" ? "Üçlü gerekli" : code}
                  </span>
                ))}
              </div>
            )}
          </>
        ) : (
          <p className="text-center text-gray-400 text-sm py-4">Skor henüz hesaplanmadı.</p>
        )}
      </div>

      {/* ── Why this recommendation ─────────────────────────────────────────── */}
      {score && (
        <div className="bg-white rounded-xl shadow p-5">
          <h2 className="text-sm font-bold text-gray-700 mb-3">Neden Bu Öneri?</h2>
          <div className="space-y-3">
            <div className="flex gap-3 items-start">
              <span className="text-lg shrink-0">🎯</span>
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-0.5">Birincil Sinyal</p>
                <p className="text-sm text-gray-800">{exp.primary_reason}</p>
              </div>
            </div>
            <div className="flex gap-3 items-start">
              <span className="text-lg shrink-0">⚠️</span>
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-0.5">Risk Faktörü</p>
                <p className="text-sm text-gray-800">{exp.risk_factor}</p>
              </div>
            </div>
            <div className="flex gap-3 items-start">
              <span className="text-lg shrink-0">🛡️</span>
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-0.5">Kapsam Gerekçesi</p>
                <p className="text-sm text-gray-800">{exp.coverage_rationale}</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Odds ────────────────────────────────────────────────────────────── */}
      {feats?.odds && (feats.odds.home || feats.odds.draw || feats.odds.away) ? (
        <div className="bg-white rounded-xl shadow p-5">
          <h2 className="text-sm font-bold text-gray-700 mb-3">Bahis Oranları</h2>
          <div className="grid grid-cols-3 gap-3 text-center">
            {([["1", feats.odds.home, BADGE["1"]], ["X", feats.odds.draw, BADGE["X"]], ["2", feats.odds.away, BADGE["2"]]] as [string, number | null, string][]).map(([label, val, cls]) => (
              <div key={label} className={`border rounded-lg p-3 ${cls}`}>
                <p className="text-lg font-bold">{label}</p>
                <p className="text-2xl font-extrabold mt-1">{val != null ? val.toFixed(2) : "—"}</p>
                {val != null && <p className="text-xs opacity-60 mt-0.5">imp. {(1 / val * 100).toFixed(0)}%</p>}
              </div>
            ))}
          </div>
          <p className="text-xs text-gray-400 mt-2 text-center">Kaynak: Bet365 · Tarihsel snapshot</p>
        </div>
      ) : (
        <div className="bg-white rounded-xl shadow p-5">
          <h2 className="text-sm font-bold text-gray-700 mb-1">Bahis Oranları</h2>
          <p className="text-xs text-gray-400">Oranlar mevcut değil — tarihsel maç veya veri henüz çekilmedi.</p>
        </div>
      )}

      {/* ── Radar + Team comparison ──────────────────────────────────────────── */}
      {feats?.home && feats?.away ? (
        <SubscriberGate>
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

            {/* Edge bars */}
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

      {/* ── Feature gauges ───────────────────────────────────────────────────── */}
      {feats ? (
        <div className="bg-white rounded-xl shadow p-5">
          <h2 className="text-sm font-bold text-gray-700 mb-3">Maç Analizi (Özellik Skorları)</h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            <Gauge label="Beraberlik Eğilimi" value={feats.draw_tendency} description="0=kesin sonuç · 100=yüksek bera. riski" />
            <Gauge label="Denge Skoru" value={feats.balance_score} description="İki takımın ne kadar dengeli olduğu" />
            <Gauge label="Düşük Tempo" value={feats.low_tempo_signal} description="Az şut / az atak beklentisi" />
            <Gauge label="Az Gol" value={feats.low_goal_signal} description="2.5 altı gol olasılığı" />
            <Gauge label="Beraberlik Tarihi" value={feats.draw_history} description="Bu iki takım arasındaki geçmiş beraberlik oranı" />
            <Gauge label="Taktik Simetri" value={feats.tactical_symmetry} description="Benzer oyun stili / taktik profil" />
            <Gauge label="Piyasa Desteği" value={feats.market_support} description="Bahis piyasasının ev sahibine verdiği ağırlık" />
            <Gauge label="Volatilite" value={feats.volatility_score} description="Tahmin güçlüğü — sürpriz riski" />
            <Gauge label="Diziliş Güveni" value={feats.lineup_certainty} description="İlk 11 bilgisinin güvenilirliği" />
            {(feats.lineup_penalty_home ?? 0) > 0.05 && (
              <Gauge label="Ev Sahibi Ceza (Eksik)" value={feats.lineup_penalty_home} description="Eksik oyuncu etkisi — 0=tam kadro" invert />
            )}
            {(feats.lineup_penalty_away ?? 0) > 0.05 && (
              <Gauge label="Deplasman Cezası (Eksik)" value={feats.lineup_penalty_away} description="Eksik oyuncu etkisi — 0=tam kadro" invert />
            )}
          </div>
        </div>
      ) : null}

      {/* ── Lineup section ────────────────────────────────────────────────────── */}
      {feats && (feats.lineup_penalty_home > 0.05 || feats.lineup_penalty_away > 0.05) ? (
        <div className="bg-white rounded-xl shadow p-5 border-l-4 border-l-amber-400">
          <h2 className="text-sm font-bold text-gray-700 mb-2">⚠ Kadro Uyarısı</h2>
          <div className="flex gap-4 text-sm">
            {feats.lineup_penalty_home > 0.05 && (
              <div className="flex-1">
                <p className="font-semibold text-blue-700">{homeTeam}</p>
                <p className="text-xs text-gray-500 mt-0.5">Eksik etkisi: <span className="font-bold text-red-500">{(feats.lineup_penalty_home * 100).toFixed(0)}/100</span></p>
              </div>
            )}
            {feats.lineup_penalty_away > 0.05 && (
              <div className="flex-1">
                <p className="font-semibold text-red-600">{awayTeam}</p>
                <p className="text-xs text-gray-500 mt-0.5">Eksik etkisi: <span className="font-bold text-red-500">{(feats.lineup_penalty_away * 100).toFixed(0)}/100</span></p>
              </div>
            )}
          </div>
        </div>
      ) : feats && feats.lineup_certainty < 0.3 ? (
        <div className="bg-gray-50 rounded-xl shadow p-4">
          <p className="text-xs text-gray-500">⏳ <strong>Kadro bilgisi henüz gelmedi</strong> — ilk 11 genellikle maçtan 2 saat önce açıklanır.</p>
        </div>
      ) : null}

      {/* ── H2H ──────────────────────────────────────────────────────────────── */}
      <div className="bg-white rounded-xl shadow p-5">
        <h2 className="text-sm font-bold text-gray-700 mb-3">Son Karşılaşmalar (H2H)</h2>
        {h2h.length === 0 ? (
          <p className="text-xs text-gray-400">Bu iki takım arasında veritabanında kayıtlı karşılaşma bulunmuyor.</p>
        ) : (
          <div className="space-y-2">
            {h2h.map((g: any, i: number) => {
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
        <SubscriberGate>
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
                  {history.map((h: any, i: number) => {
                    const prevPick = history[i + 1]?.primary_pick;
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
