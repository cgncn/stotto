"use client";

import dynamic from "next/dynamic";
import Link from "next/link";

const RadarChart = dynamic(() => import("./RadarChart"), {
  ssr: false,
  loading: () => <div style={{ height: 220 }} />,
});

const RADAR_DIMS = [
  { label: "Güç",         home: 0.85, away: 0.72 },
  { label: "Form",        home: 0.78, away: 0.68 },
  { label: "Hücum",       home: 0.80, away: 0.65 },
  { label: "Savunma",     home: 0.72, away: 0.78 },
  { label: "Motivasyon",  home: 0.82, away: 0.79 },
  { label: "Dep. Form",   home: 0.65, away: 0.70 },
  { label: "Bera. Riski", home: 0.55, away: 0.50 },
  { label: "Piyasa",      home: 0.75, away: 0.60 },
];

interface Props {
  section: "odds" | "radar" | "history";
}

const TITLES: Record<Props["section"], string> = {
  odds:    "Oran Hareketi & Sharp Money",
  radar:   "Takım Karşılaştırması",
  history: "Skor Değişim Geçmişi",
};

const ODDS_OPENS = [2.35, 3.40, 3.80];
const ODDS_DELTAS = [-0.25, -0.10, +0.15];

const HISTORY_ROWS = [
  { p1: "48%", px: "27%", p2: "25%", pick: "1", cov: "1",  conf: "%75" },
  { p1: "45%", px: "29%", p2: "26%", pick: "1", cov: "1X", conf: "%62" },
  { p1: "43%", px: "30%", p2: "27%", pick: "1", cov: "1X", conf: "%58" },
];

function OddsContent() {
  return (
    <div className="grid grid-cols-3 gap-3 mb-4">
      {(["1", "X", "2"] as const).map((label, i) => (
        <div key={label} className="border rounded-lg p-3 text-center bg-gray-50 border-gray-200">
          <p className="text-sm font-bold text-gray-500">{label}</p>
          <p className="text-xs text-gray-400 mt-0.5">Açılış</p>
          <p className="text-lg font-extrabold text-gray-600">{ODDS_OPENS[i].toFixed(2)}</p>
          <p className={`text-xs font-semibold mt-1 ${ODDS_DELTAS[i] < 0 ? "text-green-600" : "text-red-500"}`}>
            {ODDS_DELTAS[i] > 0 ? "+" : ""}{ODDS_DELTAS[i].toFixed(2)} {ODDS_DELTAS[i] < 0 ? "↓" : "↑"}
          </p>
        </div>
      ))}
    </div>
  );
}

function RadarContent() {
  return (
    <div className="flex justify-center py-4">
      <RadarChart dimensions={RADAR_DIMS} homeTeam="Ev Sahibi" awayTeam="Deplasman" size={220} />
    </div>
  );
}

function HistoryContent() {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs min-w-[480px]">
        <thead>
          <tr className="text-gray-400 border-b">
            <th className="text-left pb-2 font-medium">Tarih / Saat</th>
            <th className="text-center pb-2 font-medium text-blue-400">1</th>
            <th className="text-center pb-2 font-medium text-amber-400">X</th>
            <th className="text-center pb-2 font-medium text-red-400">2</th>
            <th className="text-center pb-2 font-medium">Birincil</th>
            <th className="text-center pb-2 font-medium">Öneri</th>
            <th className="text-center pb-2 font-medium">Güven</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {HISTORY_ROWS.map((r, i) => (
            <tr key={r.conf} className={i === 0 ? "font-semibold" : "text-gray-500"}>
              <td className="py-1.5 text-gray-400">12 Nis, 18:00</td>
              <td className="text-center text-blue-500">{r.p1}</td>
              <td className="text-center text-amber-500">{r.px}</td>
              <td className="text-center text-red-500">{r.p2}</td>
              <td className="text-center font-bold">{r.pick}</td>
              <td className="text-center">{r.cov}</td>
              <td className="text-center">{r.conf}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function BlurPlaceholder({ section }: Props) {
  return (
    <div className="bg-white rounded-xl shadow p-5">
      <h3 className="text-sm font-bold text-gray-700 mb-4">{TITLES[section]}</h3>
      <div className="relative rounded-lg overflow-hidden">
        <div className="blur-sm opacity-40 pointer-events-none select-none">
          {section === "odds"    && <OddsContent />}
          {section === "radar"   && <RadarContent />}
          {section === "history" && <HistoryContent />}
        </div>
        <div className="absolute inset-0 flex items-center justify-center bg-gradient-to-b from-white/50 to-white/85">
          <Link
            href="/uye-ol"
            className="inline-flex items-center gap-2 bg-brand-900 text-white text-sm font-semibold px-5 py-2.5 rounded-full shadow-md hover:bg-brand-700 transition-colors"
          >
            <span aria-hidden="true">🔒</span> Abone ol
          </Link>
        </div>
      </div>
    </div>
  );
}
