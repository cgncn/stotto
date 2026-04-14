"use client";

import { useState } from "react";
import { authedGet, authedPost, PoolSummary, CouponScenario } from "@/lib/api";
import CoverageBadge from "@/components/CoverageBadge";
import { SubscriberGate } from "@/components/SubscriberGate";
import { useAuth } from "@/context/AuthContext";

const SCENARIO_LABELS: Record<string, string> = {
  safe: "Güvenli",
  balanced: "Dengeli",
  aggressive: "Agresif",
};

const SCENARIO_DESC: Record<string, string> = {
  safe: "Daha fazla koruma, daha az sütun",
  balanced: "Risk ve kapsam dengesi",
  aggressive: "Yüksek kapsam, daha fazla sütun",
};

export default function KuponPage() {
  const { token } = useAuth();
  const [poolId, setPoolId] = useState<number | null>(null);
  const [scenarios, setScenarios] = useState<CouponScenario[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Custom optimizer form
  const [maxCols, setMaxCols] = useState(192);
  const [maxDoubles, setMaxDoubles] = useState(8);
  const [maxTriples, setMaxTriples] = useState(3);
  const [riskProfile, setRiskProfile] = useState("medium");
  const [customScenario, setCustomScenario] = useState<CouponScenario | null>(null);

  async function loadScenarios() {
    if (!token) { setError("Giriş yapmanız gerekiyor"); return; }
    setLoading(true);
    setError(null);
    try {
      const pool = await authedGet<PoolSummary>("/weekly-pools/current", token);
      setPoolId(pool.id);
      const data = await authedGet<CouponScenario[]>(`/weekly-pools/${pool.id}/coupon-scenarios`, token);
      // Keep one of each type
      const unique: Record<string, CouponScenario> = {};
      data.forEach((s) => {
        if (!unique[s.scenario_type]) unique[s.scenario_type] = s;
      });
      setScenarios(Object.values(unique));
    } catch (e: any) {
      setError(e.message ?? "Bağlantı hatası");
    } finally {
      setLoading(false);
    }
  }

  async function runCustomOptimize() {
    if (!poolId || !token) return;
    setLoading(true);
    setError(null);
    try {
      const result = await authedPost<CouponScenario>(
        `/weekly-pools/${poolId}/coupon-optimize`,
        { max_columns: maxCols, max_doubles: maxDoubles, max_triples: maxTriples, risk_profile: riskProfile },
        token
      );
      setCustomScenario(result);
    } catch (e: any) {
      setError(e.message ?? "Optimizasyon hatası");
    } finally {
      setLoading(false);
    }
  }

  if (scenarios.length === 0 && !loading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-4">
        <h1 className="text-2xl font-bold text-gray-800">Kupon Optimizasyonu</h1>
        <p className="text-gray-500 text-sm">Aktif haftanın kupon senaryolarını görüntüleyin.</p>
        {!token ? (
          <p className="text-amber-600 text-sm font-medium">
            Bu sayfayı kullanmak için <a href="/auth/giris" className="underline">giriş yapın</a>.
          </p>
        ) : (
          <button
            onClick={loadScenarios}
            className="bg-brand-600 text-white px-6 py-2 rounded hover:bg-brand-700 transition"
          >
            Senaryoları Yükle
          </button>
        )}
        {error && <p className="text-red-500 text-sm">{error}</p>}
      </div>
    );
  }

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-800 mb-6">Kupon Optimizasyonu</h1>

      {loading && <p className="text-gray-400 text-sm mb-4">Yükleniyor...</p>}
      {error && <p className="text-red-500 text-sm mb-4">{error}</p>}

      {/* Default scenarios */}
      <SubscriberGate>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
          {["safe", "balanced", "aggressive"].map((type) => {
            const s = scenarios.find((x) => x.scenario_type === type);
            return (
              <div key={type} className="bg-white rounded-xl shadow p-5">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-bold text-gray-800">{SCENARIO_LABELS[type]}</span>
                  {s && (
                    <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded">
                      {s.total_columns} sütun
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-400 mb-3">{SCENARIO_DESC[type]}</p>
                {s ? (
                  <>
                    {s.expected_coverage_score != null && (
                      <p className="text-xs text-gray-500 mb-3">
                        Tahmini Kapsam: %{s.expected_coverage_score.toFixed(4)}
                      </p>
                    )}
                    <div className="space-y-1">
                      {s.picks.map((p) => (
                        <div key={p.pool_match_id} className="flex items-center justify-between text-xs">
                          <span className="text-gray-500">#{p.sequence_no}</span>
                          <CoverageBadge coveragePick={p.coverage_pick} coverageType={p.coverage_type} />
                        </div>
                      ))}
                    </div>
                  </>
                ) : (
                  <p className="text-gray-300 text-xs">Senaryo henüz üretilmedi.</p>
                )}
              </div>
            );
          })}
        </div>
      </SubscriberGate>

      {/* Custom optimizer */}
      {poolId && (
        <SubscriberGate>
        <div className="bg-white rounded-xl shadow p-5">
          <h2 className="font-semibold text-gray-800 mb-4">Özel Optimizasyon</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <label className="flex flex-col text-sm gap-1">
              <span className="text-gray-500">Maks. Sütun</span>
              <input
                type="number"
                min={15}
                max={3 ** 15}
                value={maxCols}
                onChange={(e) => setMaxCols(Number(e.target.value))}
                className="border rounded px-2 py-1 text-sm"
              />
            </label>
            <label className="flex flex-col text-sm gap-1">
              <span className="text-gray-500">Maks. İkili</span>
              <input
                type="number"
                min={0}
                max={15}
                value={maxDoubles}
                onChange={(e) => setMaxDoubles(Number(e.target.value))}
                className="border rounded px-2 py-1 text-sm"
              />
            </label>
            <label className="flex flex-col text-sm gap-1">
              <span className="text-gray-500">Maks. Üçlü</span>
              <input
                type="number"
                min={0}
                max={15}
                value={maxTriples}
                onChange={(e) => setMaxTriples(Number(e.target.value))}
                className="border rounded px-2 py-1 text-sm"
              />
            </label>
            <label className="flex flex-col text-sm gap-1">
              <span className="text-gray-500">Risk Profili</span>
              <select
                value={riskProfile}
                onChange={(e) => setRiskProfile(e.target.value)}
                className="border rounded px-2 py-1 text-sm"
              >
                <option value="low">Düşük</option>
                <option value="medium">Orta</option>
                <option value="high">Yüksek</option>
              </select>
            </label>
          </div>
          <button
            onClick={runCustomOptimize}
            disabled={loading}
            className="bg-brand-600 text-white text-sm px-4 py-2 rounded hover:bg-brand-700 transition disabled:opacity-50"
          >
            Optimize Et
          </button>

          {customScenario && (
            <div className="mt-4 pt-4 border-t">
              <p className="text-sm font-semibold text-gray-700 mb-2">
                Sonuç — {customScenario.total_columns} sütun
              </p>
              <div className="grid grid-cols-5 gap-1">
                {customScenario.picks.map((p) => (
                  <div key={p.pool_match_id} className="flex flex-col items-center text-xs">
                    <span className="text-gray-400">#{p.sequence_no}</span>
                    <CoverageBadge coveragePick={p.coverage_pick} coverageType={p.coverage_type} />
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
        </SubscriberGate>
      )}
    </div>
  );
}
