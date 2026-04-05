"use client";

import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const REASON_LABELS: Record<string, string> = {
  HOME_STRENGTH: "Ev sahibi güçlü",
  AWAY_STRENGTH: "Deplasman güçlü",
  HOME_FORM: "Ev sahibi formda",
  AWAY_FORM: "Deplasman formda",
  DRAW_RISK: "Beraberlik riski yüksek",
  HOME_ABSENCE: "Ev sahibinde eksikler var",
  AWAY_ABSENCE: "Deplasmanda eksikler var",
  MARKET_ALIGNED: "Piyasa ile uyumlu",
  HIGH_VOLATILITY: "Tahmin güçlüğü yüksek",
  TRIPLE_RISK: "Üçlü kapsam gerekiyor",
  MANUAL_OVERRIDE: "Manuel müdahale uygulandı",
};

function Bar({ value, max = 1, color = "blue" }: { value: number; max?: number; color?: string }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  const colorMap: Record<string, string> = {
    blue: "bg-blue-500",
    red: "bg-red-500",
    green: "bg-green-500",
    yellow: "bg-yellow-400",
    gray: "bg-gray-400",
    indigo: "bg-indigo-500",
    orange: "bg-orange-400",
  };
  return (
    <div className="w-full bg-gray-100 rounded-full h-2">
      <div
        className={`${colorMap[color] ?? "bg-blue-500"} h-2 rounded-full transition-all`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

function StatRow({
  label,
  home,
  away,
  homeVal,
  awayVal,
  fmt = (v: number) => v.toFixed(2),
  higherIsBetter = true,
}: {
  label: string;
  home: string;
  away: string;
  homeVal: number | null | undefined;
  awayVal: number | null | undefined;
  fmt?: (v: number) => string;
  higherIsBetter?: boolean;
}) {
  const hv = homeVal ?? 0;
  const av = awayVal ?? 0;
  const max = Math.max(hv, av, 0.001);
  const homeWins = higherIsBetter ? hv >= av : hv <= av;
  return (
    <div className="py-2 border-b border-gray-50 last:border-0">
      <div className="flex justify-between items-center mb-1">
        <span className={`text-sm font-semibold ${homeWins ? "text-blue-700" : "text-gray-600"}`}>
          {fmt(hv)}
        </span>
        <span className="text-xs text-gray-400 text-center flex-1 px-2">{label}</span>
        <span className={`text-sm font-semibold ${!homeWins ? "text-red-600" : "text-gray-600"}`}>
          {fmt(av)}
        </span>
      </div>
      <div className="flex gap-1 items-center">
        <div className="flex-1">
          <div className="flex justify-end">
            <div
              className={`h-2 rounded-full ${homeWins ? "bg-blue-400" : "bg-gray-300"}`}
              style={{ width: `${Math.min(100, (hv / max) * 100)}%` }}
            />
          </div>
        </div>
        <div className="w-2" />
        <div className="flex-1">
          <div
            className={`h-2 rounded-full ${!homeWins ? "bg-red-400" : "bg-gray-300"}`}
            style={{ width: `${Math.min(100, (av / max) * 100)}%` }}
          />
        </div>
      </div>
      <div className="flex justify-between text-xs text-gray-300 mt-0.5">
        <span>{home}</span>
        <span>{away}</span>
      </div>
    </div>
  );
}

function ProbBar({ p1, px, p2, primary }: { p1: number; px: number; p2: number; primary: string }) {
  return (
    <div>
      <div className="flex h-5 rounded-lg overflow-hidden text-xs font-bold text-white">
        <div
          className="bg-blue-500 flex items-center justify-center"
          style={{ width: `${p1 * 100}%` }}
        >
          {p1 > 0.12 && `1`}
        </div>
        <div
          className="bg-amber-400 flex items-center justify-center"
          style={{ width: `${px * 100}%` }}
        >
          {px > 0.1 && `X`}
        </div>
        <div
          className="bg-red-500 flex items-center justify-center"
          style={{ width: `${p2 * 100}%` }}
        >
          {p2 > 0.12 && `2`}
        </div>
      </div>
      <div className="flex justify-between text-xs text-gray-500 mt-1">
        <span className={primary === "1" ? "font-bold text-blue-700" : ""}>{(p1 * 100).toFixed(0)}%</span>
        <span className={primary === "X" ? "font-bold text-amber-600" : ""}>{(px * 100).toFixed(0)}%</span>
        <span className={primary === "2" ? "font-bold text-red-600" : ""}>{(p2 * 100).toFixed(0)}%</span>
      </div>
    </div>
  );
}

function FeatureGauge({ label, value, description }: { label: string; value: number | null | undefined; description?: string }) {
  const v = value ?? 0;
  const pct = Math.max(0, Math.min(100, v * 100));
  const color = pct > 65 ? "bg-green-500" : pct > 40 ? "bg-yellow-400" : "bg-red-400";
  return (
    <div className="bg-gray-50 rounded-lg p-3">
      <div className="flex justify-between items-baseline mb-1">
        <span className="text-xs text-gray-500">{label}</span>
        <span className="text-sm font-bold text-gray-800">{pct.toFixed(0)}</span>
      </div>
      <div className="w-full bg-gray-200 rounded-full h-1.5">
        <div className={`${color} h-1.5 rounded-full`} style={{ width: `${pct}%` }} />
      </div>
      {description && <p className="text-xs text-gray-400 mt-1">{description}</p>}
    </div>
  );
}

export default function MatchDetailPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const poolId = searchParams.get("pool");
  const matchId = params.matchId;

  const [match, setMatch] = useState<any>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!poolId) { setError(true); return; }
    fetch(`${BASE_URL}/weekly-pools/${poolId}/matches/${matchId}`)
      .then((r) => r.ok ? r.json() : Promise.reject(r))
      .then(setMatch)
      .catch(() => setError(true));
  }, [poolId, matchId]);

  if (error) return <div className="text-center py-20 text-red-500">Maç bulunamadı</div>;
  if (!match) return <div className="text-center py-20 text-gray-400">Yükleniyor…</div>;

  const score = match.latest_score;
  const feats = match.features;
  const homeTeam = match.home_team;
  const awayTeam = match.away_team;

  const coverageColor: Record<string, string> = {
    "1": "bg-blue-100 text-blue-800",
    "X": "bg-amber-100 text-amber-800",
    "2": "bg-red-100 text-red-800",
    "1X": "bg-purple-100 text-purple-800",
    "X2": "bg-orange-100 text-orange-800",
    "12": "bg-green-100 text-green-800",
    "1X2": "bg-gray-700 text-white",
  };
  const cov = score?.recommended_coverage ?? score?.primary_pick ?? "?";

  return (
    <div className="max-w-3xl mx-auto space-y-4">
      <Link href="/" className="text-sm text-blue-600 hover:underline block">
        ← Haftalık Tablo
      </Link>

      {/* Header */}
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

        <div className="grid grid-cols-3 items-center gap-4 mb-5">
          <div className="text-center">
            <p className="text-xl font-extrabold text-gray-900">{homeTeam}</p>
            <p className="text-xs text-blue-500 mt-0.5">Ev Sahibi</p>
          </div>
          <div className="text-center text-3xl font-thin text-gray-200">VS</div>
          <div className="text-center">
            <p className="text-xl font-extrabold text-gray-900">{awayTeam}</p>
            <p className="text-xs text-red-400 mt-0.5">Deplasman</p>
          </div>
        </div>

        {score ? (
          <>
            <ProbBar p1={score.p1} px={score.px} p2={score.p2} primary={score.primary_pick} />

            <div className="mt-4 flex flex-wrap gap-3 items-center">
              <div>
                <p className="text-xs text-gray-400 mb-0.5">Öneri</p>
                <span className={`text-sm font-bold px-3 py-1 rounded-full ${coverageColor[cov] ?? "bg-gray-100 text-gray-700"}`}>
                  {cov} {cov.length > 1 ? "(İkili)" : cov === "1X2" ? "(Üçlü)" : "(Tekli)"}
                </span>
              </div>
              <div>
                <p className="text-xs text-gray-400 mb-0.5">Güven</p>
                <p className={`text-lg font-bold ${(score.confidence_score ?? 0) >= 60 ? "text-green-600" : (score.confidence_score ?? 0) >= 35 ? "text-yellow-600" : "text-red-500"}`}>
                  %{(score.confidence_score ?? 0).toFixed(0)}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-400 mb-0.5">Kapsam İhtiyacı</p>
                <p className="text-lg font-bold text-gray-700">
                  {(score.coverage_need_score ?? 0).toFixed(0)}
                  <span className="text-xs text-gray-400 ml-1">/100</span>
                </p>
              </div>
            </div>

            {score.reason_codes?.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {score.reason_codes.map((code: string) => (
                  <span key={code} className="bg-blue-50 text-blue-700 text-xs px-2 py-0.5 rounded-full border border-blue-100">
                    {REASON_LABELS[code] ?? code}
                  </span>
                ))}
              </div>
            )}
          </>
        ) : (
          <p className="text-center text-gray-400 text-sm py-4">Skor henüz hesaplanmadı.</p>
        )}
      </div>

      {/* Odds */}
      {feats?.odds && (feats.odds.home || feats.odds.draw || feats.odds.away) && (
        <div className="bg-white rounded-xl shadow p-5">
          <h2 className="text-sm font-bold text-gray-700 mb-3">Bahis Oranları (Bet365)</h2>
          <div className="grid grid-cols-3 gap-3 text-center">
            {[["1", feats.odds.home, "bg-blue-50 border-blue-200 text-blue-800"],
              ["X", feats.odds.draw, "bg-amber-50 border-amber-200 text-amber-800"],
              ["2", feats.odds.away, "bg-red-50 border-red-200 text-red-800"]].map(([label, val, cls]) => (
              <div key={label as string} className={`border rounded-lg p-3 ${cls as string}`}>
                <p className="text-xl font-bold">{label}</p>
                <p className="text-2xl font-extrabold mt-1">{val ? (val as number).toFixed(2) : "—"}</p>
                {val && <p className="text-xs opacity-70 mt-0.5">imp. {(1 / (val as number) * 100).toFixed(0)}%</p>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Team Comparison */}
      {feats?.home && feats?.away && (
        <div className="bg-white rounded-xl shadow p-5">
          <h2 className="text-sm font-bold text-gray-700 mb-1">Takım Karşılaştırması</h2>
          <div className="flex justify-between text-xs font-bold text-gray-400 mb-2">
            <span className="text-blue-600">{homeTeam}</span>
            <span className="text-red-500">{awayTeam}</span>
          </div>
          <StatRow label="Güç Skoru" home={homeTeam} away={awayTeam}
            homeVal={feats.home.strength_score} awayVal={feats.away.strength_score}
            fmt={(v) => (v * 100).toFixed(0)} />
          <StatRow label="Form Skoru" home={homeTeam} away={awayTeam}
            homeVal={feats.home.form_score} awayVal={feats.away.form_score}
            fmt={(v) => (v * 100).toFixed(0)} />
          <StatRow label="Maç Başı Puan" home={homeTeam} away={awayTeam}
            homeVal={feats.home.season_ppg} awayVal={feats.away.season_ppg}
            fmt={(v) => v.toFixed(2)} />
          <StatRow label="Gol Farkı / Maç" home={homeTeam} away={awayTeam}
            homeVal={feats.home.goal_diff_per_game} awayVal={feats.away.goal_diff_per_game}
            fmt={(v) => (v > 0 ? "+" : "") + v.toFixed(2)} />
          <StatRow label="Hücum Gücü" home={homeTeam} away={awayTeam}
            homeVal={feats.home.attack_index} awayVal={feats.away.attack_index}
            fmt={(v) => (v * 100).toFixed(0)} />
          <StatRow label="Savunma Gücü" home={homeTeam} away={awayTeam}
            homeVal={feats.home.defense_index} awayVal={feats.away.defense_index}
            fmt={(v) => (v * 100).toFixed(0)} />
        </div>
      )}

      {/* Feature Gauges */}
      {feats && (
        <div className="bg-white rounded-xl shadow p-5">
          <h2 className="text-sm font-bold text-gray-700 mb-3">Maç Analizi</h2>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            <FeatureGauge label="Beraberlik Eğilimi" value={feats.draw_tendency} description="Yüksek = beraberlik riski" />
            <FeatureGauge label="Denge Skoru" value={feats.balance_score} description="Takımlar ne kadar dengeli" />
            <FeatureGauge label="Düşük Tempo" value={feats.low_tempo_signal} description="Az sayıda şut beklentisi" />
            <FeatureGauge label="Az Gol" value={feats.low_goal_signal} description="2.5 altı gol beklentisi" />
            <FeatureGauge label="Beraberlik Tarihi" value={feats.draw_history} description="Geçmiş maçlarda beraberlik oranı" />
            <FeatureGauge label="Taktik Simetri" value={feats.tactical_symmetry} description="Benzer taktik profil" />
            <FeatureGauge label="Piyasa Desteği" value={feats.market_support} description="Bahis piyasasının 1 görüşü" />
            <FeatureGauge label="Volatilite" value={feats.volatility_score} description="Tahmin belirsizliği" />
            <FeatureGauge label="Diziliş Güveni" value={feats.lineup_certainty} description="İlk 11 bilgisinin güvenilirliği" />
            {feats.lineup_penalty_home > 0 && (
              <FeatureGauge label="Ev Sahibi Ceza" value={feats.lineup_penalty_home} description="Eksik oyuncu etkisi" />
            )}
            {feats.lineup_penalty_away > 0 && (
              <FeatureGauge label="Deplasman Cezası" value={feats.lineup_penalty_away} description="Eksik oyuncu etkisi" />
            )}
          </div>

          {/* Strength / Form edges */}
          <div className="mt-4 space-y-3">
            <div>
              <div className="flex justify-between text-xs text-gray-500 mb-1">
                <span>← {awayTeam} üstün</span>
                <span className="font-semibold text-gray-700">Güç Farkı</span>
                <span>{homeTeam} üstün →</span>
              </div>
              <div className="relative h-3 bg-gray-100 rounded-full overflow-hidden">
                <div className="absolute inset-y-0 left-1/2 w-px bg-gray-300" />
                {(feats.strength_edge ?? 0) >= 0 ? (
                  <div
                    className="absolute inset-y-0 bg-blue-400 rounded-full"
                    style={{ left: "50%", width: `${Math.min(50, Math.abs((feats.strength_edge ?? 0)) * 50)}%` }}
                  />
                ) : (
                  <div
                    className="absolute inset-y-0 bg-red-400 rounded-full"
                    style={{ right: "50%", width: `${Math.min(50, Math.abs((feats.strength_edge ?? 0)) * 50)}%` }}
                  />
                )}
              </div>
              <p className="text-center text-xs text-gray-500 mt-0.5">
                {(feats.strength_edge ?? 0) > 0 ? `${homeTeam} +${((feats.strength_edge ?? 0) * 100).toFixed(0)} puan üstün` :
                  (feats.strength_edge ?? 0) < 0 ? `${awayTeam} +${(Math.abs(feats.strength_edge ?? 0) * 100).toFixed(0)} puan üstün` :
                    "Dengeli"}
              </p>
            </div>

            <div>
              <div className="flex justify-between text-xs text-gray-500 mb-1">
                <span>← {awayTeam} formda</span>
                <span className="font-semibold text-gray-700">Form Farkı</span>
                <span>{homeTeam} formda →</span>
              </div>
              <div className="relative h-3 bg-gray-100 rounded-full overflow-hidden">
                <div className="absolute inset-y-0 left-1/2 w-px bg-gray-300" />
                {(feats.form_edge ?? 0) >= 0 ? (
                  <div
                    className="absolute inset-y-0 bg-blue-400 rounded-full"
                    style={{ left: "50%", width: `${Math.min(50, Math.abs((feats.form_edge ?? 0)) * 50)}%` }}
                  />
                ) : (
                  <div
                    className="absolute inset-y-0 bg-red-400 rounded-full"
                    style={{ right: "50%", width: `${Math.min(50, Math.abs((feats.form_edge ?? 0)) * 50)}%` }}
                  />
                )}
              </div>
              <p className="text-center text-xs text-gray-500 mt-0.5">
                {(feats.form_edge ?? 0) > 0 ? `${homeTeam} son formuyla daha iyi` :
                  (feats.form_edge ?? 0) < 0 ? `${awayTeam} son formuyla daha iyi` :
                    "Benzer form"}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Score history */}
      {match.score_history?.length > 1 && (
        <div className="bg-white rounded-xl shadow p-5">
          <h2 className="text-sm font-bold text-gray-700 mb-3">Skor Değişim Geçmişi</h2>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-gray-400 border-b">
                <th className="text-left pb-2">Tarih / Saat</th>
                <th className="text-center pb-2">1</th>
                <th className="text-center pb-2">X</th>
                <th className="text-center pb-2">2</th>
                <th className="text-center pb-2">Birincil</th>
                <th className="text-center pb-2">Öneri</th>
                <th className="text-center pb-2">Güven</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {match.score_history.map((h: any, i: number) => (
                <tr key={i} className={i === 0 ? "font-semibold" : "text-gray-500"}>
                  <td className="py-1.5">
                    {new Date(h.created_at).toLocaleString("tr-TR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                  </td>
                  <td className="text-center text-blue-600">{(h.p1 * 100).toFixed(0)}%</td>
                  <td className="text-center text-amber-600">{(h.px * 100).toFixed(0)}%</td>
                  <td className="text-center text-red-500">{(h.p2 * 100).toFixed(0)}%</td>
                  <td className="text-center font-bold">{h.primary_pick}</td>
                  <td className="text-center">{h.coverage_pick ?? "—"}</td>
                  <td className="text-center">{h.confidence_score != null ? `%${h.confidence_score.toFixed(0)}` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
