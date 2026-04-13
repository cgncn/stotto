"use client";

import { useState } from "react";

interface MatchResultRow {
  sequence_no: number;
  home_team: string;
  away_team: string;
  kickoff_at: string | null;
  result: string | null;
  home_score: number | null;
  away_score: number | null;
  primary_pick: string | null;
  p1: number | null;
  px: number | null;
  p2: number | null;
  confidence_score: number | null;
  correct: boolean | null;
}

interface PoolAccuracySummary {
  id: number;
  week_code: string;
  created_at: string;
  match_count: number;
  scored_count: number;
  correct_count: number;
  brier_score: number | null;
  avg_confidence: number | null;
}

interface Props {
  pool: PoolAccuracySummary;
  rows: MatchResultRow[];
}

function brierColor(score: number | null): string {
  if (score === null) return "text-zinc-500";
  if (score < 0.28) return "text-green-400";
  if (score <= 0.33) return "text-amber-400";
  return "text-red-400";
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("tr-TR", { day: "numeric", month: "short", year: "numeric" });
  } catch {
    return iso;
  }
}

export default function PoolHistoryCard({ pool, rows }: Props) {
  const [expanded, setExpanded] = useState(false);

  const accuracy =
    pool.scored_count > 0 ? Math.round((pool.correct_count / pool.scored_count) * 100) : null;
  const scoredRows = rows.filter((r) => r.primary_pick !== null);

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
      {/* Summary row */}
      <div className="px-5 py-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-base font-semibold text-white font-mono">{pool.week_code}</div>
            <div className="text-xs text-zinc-500 mt-0.5">
              Kapandı: {formatDate(pool.created_at)}
            </div>
          </div>

          <div className="flex flex-col items-end gap-1 min-w-[160px]">
            <div className="text-xs text-zinc-400">Tahmin Doğruluğu</div>
            {pool.scored_count > 0 ? (
              <>
                <div className="flex items-center gap-2 w-full">
                  <div className="flex-1 bg-zinc-700 rounded-full h-2 overflow-hidden">
                    <div
                      className="bg-blue-500 h-2 rounded-full transition-all"
                      style={{ width: `${accuracy}%` }}
                    />
                  </div>
                  <span className="text-xs text-white font-medium w-8 text-right">{accuracy}%</span>
                </div>
                <div className="text-[10px] text-zinc-500">
                  {pool.correct_count}/{pool.scored_count} tahmin
                </div>
                <div className="flex gap-3 text-[10px] mt-1">
                  <span>
                    Brier:{" "}
                    <span className={brierColor(pool.brier_score)}>
                      {pool.brier_score !== null ? pool.brier_score.toFixed(3) : "—"}
                    </span>
                  </span>
                  <span className="text-zinc-500">
                    Güven Ort:{" "}
                    <span className="text-zinc-300">
                      {pool.avg_confidence !== null ? Math.round(pool.avg_confidence) : "—"}
                    </span>
                  </span>
                </div>
              </>
            ) : (
              <div className="text-xs text-zinc-600">Tahmin yok</div>
            )}
          </div>
        </div>

        {scoredRows.length > 0 && (
          <button
            onClick={() => setExpanded((v) => !v)}
            className="mt-3 text-xs text-blue-400 hover:text-blue-300 transition-colors flex items-center gap-1"
          >
            {expanded ? "Gizle" : "Detayları Gör"}{" "}
            <span className="text-[10px]">{expanded ? "▲" : "▾"}</span>
          </button>
        )}
      </div>

      {/* Detail table */}
      {expanded && scoredRows.length > 0 && (
        <div className="border-t border-zinc-800 overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-zinc-500 text-[10px] uppercase tracking-wider border-b border-zinc-800">
                <th className="px-3 py-2 text-left w-6">#</th>
                <th className="px-3 py-2 text-left">Ev – Dep</th>
                <th className="px-3 py-2 text-center">Skor</th>
                <th className="px-3 py-2 text-center">Sonuç</th>
                <th className="px-3 py-2 text-center">Tahmin</th>
                <th className="px-3 py-2 text-center">P1</th>
                <th className="px-3 py-2 text-center">PX</th>
                <th className="px-3 py-2 text-center">P2</th>
                <th className="px-3 py-2 text-center">Güven</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/50">
              {scoredRows.map((row) => (
                <tr key={row.sequence_no} className="hover:bg-zinc-800/30 transition-colors">
                  <td className="px-3 py-2 text-zinc-600 font-mono">{row.sequence_no}</td>
                  <td className="px-3 py-2 text-zinc-300 max-w-[180px] truncate">
                    {row.home_team} – {row.away_team}
                  </td>
                  <td className="px-3 py-2 text-center text-zinc-400 font-mono">
                    {row.home_score !== null && row.away_score !== null
                      ? `${row.home_score}-${row.away_score}`
                      : "—"}
                  </td>
                  <td className="px-3 py-2 text-center font-mono text-zinc-300">
                    {row.result ?? <span className="text-zinc-600">—</span>}
                  </td>
                  <td className="px-3 py-2 text-center font-mono font-semibold">
                    {row.primary_pick ? (
                      row.correct === true ? (
                        <span className="text-green-400">{row.primary_pick} ✓</span>
                      ) : row.correct === false ? (
                        <span className="text-red-400">{row.primary_pick} ✗</span>
                      ) : (
                        <span className="text-zinc-300">{row.primary_pick}</span>
                      )
                    ) : (
                      <span className="text-zinc-600">—</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-center text-zinc-400">
                    {row.p1 !== null ? `${Math.round(row.p1 * 100)}%` : "—"}
                  </td>
                  <td className="px-3 py-2 text-center text-zinc-400">
                    {row.px !== null ? `${Math.round(row.px * 100)}%` : "—"}
                  </td>
                  <td className="px-3 py-2 text-center text-zinc-400">
                    {row.p2 !== null ? `${Math.round(row.p2 * 100)}%` : "—"}
                  </td>
                  <td className="px-3 py-2 text-center text-zinc-500">
                    {row.confidence_score !== null ? Math.round(row.confidence_score) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
