import Link from "next/link";
import { get, PoolMatch, PoolSummary } from "@/lib/api";
import ProbabilityBar from "@/components/ProbabilityBar";
import CoverageBadge from "@/components/CoverageBadge";

export const revalidate = 60; // ISR: refresh every 60 seconds

async function getData(): Promise<{ pool: PoolSummary | null; matches: PoolMatch[] }> {
  try {
    const pool = await get<PoolSummary>("/weekly-pools/current");
    const matches = await get<PoolMatch[]>(`/weekly-pools/${pool.id}`);
    return { pool, matches };
  } catch {
    return { pool: null, matches: [] };
  }
}

function ConfidenceChip({ score }: { score: number | null }) {
  if (score === null) return null;
  const cls =
    score >= 70
      ? "bg-green-100 text-green-700"
      : score >= 45
      ? "bg-yellow-100 text-yellow-700"
      : "bg-red-100 text-red-700";
  return (
    <span className={`text-xs font-medium px-1.5 py-0.5 rounded ${cls}`}>
      %{score.toFixed(0)}
    </span>
  );
}

export default async function HomePage() {
  const { pool, matches } = await getData();

  if (!pool) {
    return (
      <div className="text-center py-20 text-gray-500">
        <p className="text-2xl font-semibold mb-2">Aktif hafta bulunamadı</p>
        <p className="text-sm">Spor Toto havuzu henüz oluşturulmadı.</p>
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{pool.week_code}</h1>
          <p className="text-sm text-gray-500">
            {pool.match_count} maç · {pool.locked_count} kilitli
          </p>
        </div>
        <Link
          href="/kupon"
          className="bg-brand-600 text-white text-sm px-4 py-2 rounded hover:bg-brand-700 transition"
        >
          Kupon Optimizasyonu →
        </Link>
      </div>

      {/* Match table */}
      <div className="overflow-x-auto rounded-lg shadow">
        <table className="w-full bg-white text-sm">
          <thead className="bg-gray-100 text-gray-600 uppercase text-xs">
            <tr>
              <th className="px-3 py-2 text-left w-6">#</th>
              <th className="px-3 py-2 text-left">Ev Sahibi</th>
              <th className="px-3 py-2 text-left">Deplasman</th>
              <th className="px-3 py-2 text-left w-40">Olasılık</th>
              <th className="px-3 py-2 text-center">Öneri</th>
              <th className="px-3 py-2 text-center">Güven</th>
              <th className="px-3 py-2 text-center">Kapsam</th>
              <th className="px-3 py-2 text-center">Durum</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {matches.map((m) => {
              const score = m.latest_score;
              return (
                <tr
                  key={m.id}
                  className={`hover:bg-blue-50 transition ${m.is_locked ? "opacity-60" : ""}`}
                >
                  <td className="px-3 py-2 font-mono text-gray-400">{m.sequence_no}</td>
                  <td className="px-3 py-2 font-medium">{m.home_team || "—"}</td>
                  <td className="px-3 py-2 text-gray-700">{m.away_team || "—"}</td>
                  <td className="px-3 py-2">
                    {score ? (
                      <ProbabilityBar
                        p1={score.p1}
                        px={score.px}
                        p2={score.p2}
                        primaryPick={score.primary_pick}
                      />
                    ) : (
                      <span className="text-gray-300 text-xs">Hesaplanıyor...</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-center">
                    {score?.recommended_coverage ? (
                      <CoverageBadge
                        coveragePick={score.recommended_coverage}
                        coverageType={
                          score.recommended_coverage.length === 1
                            ? "single"
                            : score.recommended_coverage === "1X2"
                            ? "triple"
                            : "double"
                        }
                      />
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="px-3 py-2 text-center">
                    <ConfidenceChip score={score?.confidence_score ?? null} />
                  </td>
                  <td className="px-3 py-2 text-center">
                    {score?.coverage_need_score != null ? (
                      <span className="text-xs text-gray-600">
                        {score.coverage_need_score.toFixed(0)}
                      </span>
                    ) : "—"}
                  </td>
                  <td className="px-3 py-2 text-center">
                    {m.is_locked ? (
                      <span className="text-xs bg-gray-200 text-gray-600 px-1.5 py-0.5 rounded">
                        {m.result ?? "Kilitli"}
                      </span>
                    ) : (
                      <Link
                        href={`/mac/${m.id}?pool=${pool.id}`}
                        className="text-xs text-blue-600 hover:underline"
                      >
                        Detay
                      </Link>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
