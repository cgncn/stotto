"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import ConfidenceRing from "./ConfidenceRing";
import { buildExplanation } from "@/lib/explanation";
import type { PoolMatch, PoolSummary } from "@/lib/api";

// ── Types ─────────────────────────────────────────────────────────────────────

type SortKey = "seq" | "p1" | "px" | "p2" | "confidence" | "coverage_need";
type SortDir = "asc" | "desc";
type Filter = "all" | "riskiest" | "single" | "draw" | "derby" | "sharp_money" | "post_break";

// ── Constants ──────────────────────────────────────────────────────────────────

const BORDER_COLOR: Record<string, string> = {
  "1":   "border-l-blue-500",
  "X":   "border-l-amber-400",
  "2":   "border-l-red-500",
  "1X":  "border-l-purple-500",
  "X2":  "border-l-orange-400",
  "12":  "border-l-green-500",
  "1X2": "border-l-gray-500",
};

const BADGE_COLOR: Record<string, string> = {
  "1":   "bg-blue-100 text-blue-800 border-blue-200",
  "X":   "bg-amber-100 text-amber-800 border-amber-200",
  "2":   "bg-red-100 text-red-800 border-red-200",
  "1X":  "bg-purple-100 text-purple-800 border-purple-200",
  "X2":  "bg-orange-100 text-orange-800 border-orange-200",
  "12":  "bg-green-100 text-green-800 border-green-200",
  "1X2": "bg-gray-200 text-gray-800 border-gray-300",
};

// ── Sub-components ─────────────────────────────────────────────────────────────

function ProbMini({ p1, px, p2, primary }: { p1: number; px: number; p2: number; primary: string }) {
  return (
    <div className="w-full">
      <div className="flex h-2 rounded overflow-hidden gap-px">
        <div className="bg-blue-400" style={{ width: `${p1 * 100}%` }} />
        <div className="bg-amber-400" style={{ width: `${px * 100}%` }} />
        <div className="bg-red-400" style={{ width: `${p2 * 100}%` }} />
      </div>
      <div className="flex justify-between text-[10px] text-gray-400 mt-0.5">
        <span className={primary === "1" ? "font-bold text-blue-600" : ""}>{(p1 * 100).toFixed(0)}%</span>
        <span className={primary === "X" ? "font-bold text-amber-600" : ""}>{(px * 100).toFixed(0)}%</span>
        <span className={primary === "2" ? "font-bold text-red-500" : ""}>{(p2 * 100).toFixed(0)}%</span>
      </div>
    </div>
  );
}

function SortBtn({
  col, current, dir, onSort,
}: {
  col: SortKey; current: SortKey; dir: SortDir; onSort: (k: SortKey) => void;
}) {
  const active = col === current;
  return (
    <button
      onClick={() => onSort(col)}
      className={`flex items-center gap-0.5 text-xs font-medium ${active ? "text-blue-600" : "text-gray-400 hover:text-gray-600"}`}
    >
      {col === "seq" ? "#" : col === "p1" ? "1" : col === "px" ? "X" : col === "p2" ? "2" : col === "confidence" ? "Güven" : "Kapsam"}
      <span className="text-[10px]">
        {active ? (dir === "asc" ? " ↑" : " ↓") : " ↕"}
      </span>
    </button>
  );
}

function ChangeArrow({ history }: { history?: { primary_pick: string }[] }) {
  if (!history || history.length < 2) return null;
  const latest = history[0].primary_pick;
  const prev = history[1].primary_pick;
  if (latest === prev) return null;
  return (
    <span
      title={`${prev} → ${latest}`}
      className="ml-1 text-amber-500 font-bold text-xs animate-pulse"
    >
      ⚡
    </span>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function MatchTable({
  pool,
  matches,
  refreshedAt,
}: {
  pool: PoolSummary;
  matches: PoolMatch[];
  refreshedAt: string;
}) {
  const [sortKey, setSortKey] = useState<SortKey>("seq");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [filter, setFilter] = useState<Filter>("all");

  function handleSort(key: SortKey) {
    if (key === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(key); setSortDir(key === "seq" ? "asc" : "desc"); }
  }

  const filtered = useMemo(() => {
    let list = [...matches];
    if (filter === "riskiest") {
      list = list.filter((m) => (m.latest_score?.coverage_need_score ?? 0) > 55);
    } else if (filter === "single") {
      list = list.filter((m) => {
        const cov = m.latest_score?.recommended_coverage ?? "";
        return cov.length === 1;
      });
    } else if (filter === "draw") {
      list = list.filter((m) => m.latest_score?.primary_pick === "X");
    } else if (filter === "derby") {
      list = list.filter((m) => m.is_derby);
    } else if (filter === "sharp_money") {
      list = list.filter((m) => m.sharp_money_flag === true);
    } else if (filter === "post_break") {
      list = list.filter((m) => m.post_intl_break === true);
    }

    list.sort((a, b) => {
      const sa = a.latest_score;
      const sb = b.latest_score;
      let va = 0, vb = 0;
      if (sortKey === "seq") { va = a.sequence_no; vb = b.sequence_no; }
      else if (sortKey === "p1") { va = sa?.p1 ?? 0; vb = sb?.p1 ?? 0; }
      else if (sortKey === "px") { va = sa?.px ?? 0; vb = sb?.px ?? 0; }
      else if (sortKey === "p2") { va = sa?.p2 ?? 0; vb = sb?.p2 ?? 0; }
      else if (sortKey === "confidence") { va = sa?.confidence_score ?? 0; vb = sb?.confidence_score ?? 0; }
      else if (sortKey === "coverage_need") { va = sa?.coverage_need_score ?? 0; vb = sb?.coverage_need_score ?? 0; }
      return sortDir === "asc" ? va - vb : vb - va;
    });
    return list;
  }, [matches, filter, sortKey, sortDir]);

  const FILTERS: { key: Filter; label: string }[] = [
    { key: "all", label: "Tümü" },
    { key: "riskiest", label: "⚠ En Riskli" },
    { key: "single", label: "✓ Tekli Aday" },
    { key: "draw", label: "≡ Beraberlik Adayı" },
    { key: "derby", label: "🔥 Derby" },
    { key: "sharp_money", label: "📈 Sharp Money" },
    { key: "post_break", label: "🌍 Milli Ara Sonrası" },
  ];

  return (
    <div>
      {/* Header bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{pool.week_code}</h1>
          <p className="text-xs text-gray-400 mt-0.5">
            {pool.match_count} maç · {pool.locked_count} kilitli ·{" "}
            <span className="text-gray-500">
              Son güncelleme: {new Date(refreshedAt).toLocaleString("tr-TR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
            </span>
          </p>
        </div>
        <Link
          href="/kupon"
          className="inline-flex items-center gap-1.5 bg-blue-600 text-white text-sm font-semibold px-4 py-2 rounded-lg hover:bg-blue-700 transition self-start sm:self-auto"
        >
          Kupon Optimizasyonu →
        </Link>
      </div>

      {/* Filter chips */}
      <div className="flex flex-wrap gap-2 mb-3">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={`text-xs px-3 py-1 rounded-full border font-medium transition ${
              filter === f.key
                ? "bg-blue-600 text-white border-blue-600"
                : "bg-white text-gray-600 border-gray-200 hover:border-blue-300"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Sort bar — desktop */}
      <div className="hidden sm:flex items-center gap-4 px-4 py-1.5 bg-gray-50 rounded-lg mb-1 text-xs text-gray-400">
        <SortBtn col="seq" current={sortKey} dir={sortDir} onSort={handleSort} />
        <span className="flex-1 text-gray-400">Maç</span>
        <div className="flex gap-3">
          <SortBtn col="p1" current={sortKey} dir={sortDir} onSort={handleSort} />
          <SortBtn col="px" current={sortKey} dir={sortDir} onSort={handleSort} />
          <SortBtn col="p2" current={sortKey} dir={sortDir} onSort={handleSort} />
        </div>
        <SortBtn col="confidence" current={sortKey} dir={sortDir} onSort={handleSort} />
        <SortBtn col="coverage_need" current={sortKey} dir={sortDir} onSort={handleSort} />
        <span className="w-16 text-center">Detay</span>
      </div>

      {/* Match cards */}
      <div className="space-y-2">
        {filtered.length === 0 && (
          <p className="text-center py-8 text-gray-400 text-sm">Bu filtreye uyan maç bulunamadı.</p>
        )}
        {filtered.map((m) => {
          const s = m.latest_score;
          const cov = s?.recommended_coverage ?? s?.primary_pick ?? "?";
          const borderCls = BORDER_COLOR[cov] ?? "border-l-gray-300";
          const badgeCls = BADGE_COLOR[cov] ?? "bg-gray-100 text-gray-700";
          const exp = buildExplanation(null, s, m.home_team, m.away_team);
          const hasData = s != null;
          const history = (m as any).score_history as { primary_pick: string }[] | undefined;

          return (
            <div
              key={m.id}
              className={`bg-white rounded-xl shadow-sm border-l-4 ${borderCls} overflow-hidden`}
            >
              {/* Desktop layout */}
              <div className="hidden sm:flex items-center gap-4 px-4 py-3">
                {/* Seq */}
                <span className="w-5 text-xs font-mono text-gray-400 shrink-0">{m.sequence_no}</span>

                {/* Teams + explanation */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="font-semibold text-gray-900 text-sm truncate">{m.home_team}</span>
                    <span className="text-gray-300 text-xs">vs</span>
                    <span className="font-semibold text-gray-900 text-sm truncate">{m.away_team}</span>
                    {m.is_derby && <span className="shrink-0 text-[9px] font-bold px-1.5 py-0.5 rounded-full bg-orange-100 text-orange-700 border border-orange-200">DERBY</span>}
                    {m.post_intl_break && <span className="shrink-0 text-[9px] px-1.5 py-0.5 rounded-full bg-blue-50 text-blue-500 border border-blue-100">🌍 Milli Ara</span>}
                    <ChangeArrow history={history} />
                  </div>
                  {hasData ? (
                    <p className="text-xs text-gray-400 mt-0.5 line-clamp-1">{exp.primary_reason}</p>
                  ) : (
                    <p className="text-xs text-gray-300 mt-0.5">Veri bekleniyor…</p>
                  )}
                </div>

                {/* Prob bar */}
                <div className="w-36 shrink-0">
                  {hasData ? (
                    <ProbMini p1={s!.p1} px={s!.px} p2={s!.p2} primary={s!.primary_pick} />
                  ) : (
                    <div className="h-4 bg-gray-100 rounded animate-pulse" />
                  )}
                </div>

                {/* Coverage badge */}
                <div className="w-20 shrink-0 flex justify-center">
                  {hasData ? (
                    <div className="flex flex-col items-center gap-0.5">
                      <span className={`text-xs font-bold px-2 py-0.5 rounded-full border ${badgeCls}`}>{cov}</span>
                      {cov !== s!.primary_pick && (
                        <span className="text-[10px] text-gray-400">{s!.primary_pick} → {cov}</span>
                      )}
                    </div>
                  ) : (
                    <span className="text-gray-300 text-xs">—</span>
                  )}
                </div>

                {/* Confidence ring */}
                <div className="w-14 shrink-0 flex justify-center">
                  {hasData ? (
                    <ConfidenceRing score={s!.confidence_score} pick={s!.primary_pick} size={48} />
                  ) : (
                    <div className="w-12 h-12 rounded-full bg-gray-100 animate-pulse" />
                  )}
                </div>

                {/* Coverage need */}
                <div className="w-16 shrink-0 text-center">
                  {hasData && s!.coverage_need_score != null ? (
                    <div>
                      <div className="text-xs font-bold text-gray-700">{s!.coverage_need_score.toFixed(0)}</div>
                      <div className="w-full bg-gray-100 rounded-full h-1 mt-0.5">
                        <div
                          className={`h-1 rounded-full ${s!.coverage_need_score > 65 ? "bg-red-400" : s!.coverage_need_score > 40 ? "bg-amber-400" : "bg-green-400"}`}
                          style={{ width: `${s!.coverage_need_score}%` }}
                        />
                      </div>
                    </div>
                  ) : (
                    <span className="text-gray-300 text-xs">—</span>
                  )}
                </div>

                {/* Detay link */}
                <Link
                  href={`/mac/${m.id}?pool=${pool.id}`}
                  className="w-14 shrink-0 text-center text-xs font-medium text-blue-600 hover:text-blue-800 hover:underline"
                >
                  Detay →
                </Link>
              </div>

              {/* Mobile layout */}
              <div className="flex sm:hidden items-start gap-3 px-3 py-3">
                <div className="shrink-0 mt-1">
                  {hasData ? (
                    <ConfidenceRing score={s!.confidence_score} pick={s!.primary_pick} size={44} />
                  ) : (
                    <div className="w-11 h-11 rounded-full bg-gray-100 animate-pulse" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1 mb-0.5 flex-wrap">
                    <span className="text-xs text-gray-400 font-mono">{m.sequence_no}.</span>
                    <span className="font-semibold text-sm text-gray-900 truncate">{m.home_team}</span>
                    <span className="text-gray-300 text-xs">vs</span>
                    <span className="font-semibold text-sm text-gray-900 truncate">{m.away_team}</span>
                    {m.is_derby && <span className="shrink-0 text-[9px] font-bold px-1.5 py-0.5 rounded-full bg-orange-100 text-orange-700 border border-orange-200">DERBY</span>}
                    <ChangeArrow history={history} />
                  </div>
                  {hasData && (
                    <>
                      <ProbMini p1={s!.p1} px={s!.px} p2={s!.p2} primary={s!.primary_pick} />
                      <p className="text-xs text-gray-400 mt-1 line-clamp-2">{exp.primary_reason}</p>
                    </>
                  )}
                </div>
                <div className="shrink-0 flex flex-col items-end gap-1">
                  {hasData && (
                    <span className={`text-xs font-bold px-2 py-0.5 rounded-full border ${badgeCls}`}>{cov}</span>
                  )}
                  <Link href={`/mac/${m.id}?pool=${pool.id}`} className="text-xs text-blue-600 font-medium">Detay →</Link>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
