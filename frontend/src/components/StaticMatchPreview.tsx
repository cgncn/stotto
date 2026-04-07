// frontend/src/components/StaticMatchPreview.tsx
"use client";

import dynamic from "next/dynamic";
import ConfidenceRing from "./ConfidenceRing";

const RadarChart = dynamic(() => import("./RadarChart"), {
  ssr: false,
  loading: () => <div style={{ height: 240 }} />,
});

// ── Static demo data ──────────────────────────────────────────────────────────

const DEMO = {
  home: "GALATASARAY",
  away: "FENERBAHÇE",
  week: "Hf 28",
  seq: 7,
  kickoff: "Pazar · 20:45",
  isDerby: true,
  p1: 0.482,
  px: 0.271,
  p2: 0.247,
  primary: "1",
  confidence: 75,
  reasons: ["Ev güçlü", "Piyasa uyumlu", "Derby maçı", "H2H ev üstün"],
  motivation: {
    home: 0.82,
    away: 0.79,
    homeLabel: "Şampiyonluk yarışı",
    awayLabel: "Şampiyonluk yarışı",
  },
  radarDims: [
    { label: "Güç",         home: 0.85, away: 0.72 },
    { label: "Form",        home: 0.78, away: 0.68 },
    { label: "Hücum",       home: 0.80, away: 0.65 },
    { label: "Savunma",     home: 0.72, away: 0.78 },
    { label: "Motivasyon",  home: 0.82, away: 0.79 },
    { label: "Dep. Form",   home: 0.65, away: 0.70 },
    { label: "Bera. Riski", home: 0.55, away: 0.50 },
    { label: "Piyasa",      home: 0.75, away: 0.60 },
  ],
  odds: {
    homeOpen: 2.35, homeCurrent: 2.10,
    drawOpen: 3.40, drawCurrent: 3.30,
    awayOpen: 3.80, awayCurrent: 3.95,
  },
  sharpSignal: -0.6,
  xg: { home: 1.82, away: 1.21 },
  h2h: {
    results: ["W", "W", "D", "L", "W"] as ("W" | "D" | "L")[],
    homeWinPct: 0.55,
    drawPct: 0.20,
    awayWinPct: 0.25,
  },
};

const ODDS_LABELS = ["1", "X", "2"] as const;
const ODDS_OPENS = [DEMO.odds.homeOpen, DEMO.odds.drawOpen, DEMO.odds.awayOpen];
const ODDS_CURRENTS = [DEMO.odds.homeCurrent, DEMO.odds.drawCurrent, DEMO.odds.awayCurrent];

const BADGE: Record<string, string> = {
  "1": "bg-blue-100 text-blue-800 border-blue-200",
  "X": "bg-amber-100 text-amber-800 border-amber-200",
  "2": "bg-red-100 text-red-800 border-red-200",
};

// ── Sub-components ────────────────────────────────────────────────────────────

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3 pt-4 border-t border-gray-50">
      {children}
    </h3>
  );
}

function ProbBar() {
  const { p1, px, p2, primary } = DEMO;
  return (
    <div>
      <div className="flex h-6 rounded-lg overflow-hidden">
        <div className="bg-blue-500 flex items-center justify-center text-white text-xs font-bold" style={{ width: `${p1 * 100}%` }}>1</div>
        <div className="bg-amber-400 flex items-center justify-center text-white text-xs font-bold" style={{ width: `${px * 100}%` }}>X</div>
        <div className="bg-red-500 flex items-center justify-center text-white text-xs font-bold" style={{ width: `${p2 * 100}%` }}>2</div>
      </div>
      <div className="flex justify-between text-sm mt-1.5 font-semibold">
        <span className={primary === "1" ? "text-blue-700" : "text-gray-500"}>{(p1 * 100).toFixed(1)}%</span>
        <span className={primary === "X" ? "text-amber-600" : "text-gray-500"}>{(px * 100).toFixed(1)}%</span>
        <span className={primary === "2" ? "text-red-600" : "text-gray-500"}>{(p2 * 100).toFixed(1)}%</span>
      </div>
    </div>
  );
}

function MotivationGauge({ label, score, sublabel, color }: { label: string; score: number; sublabel: string; color: "blue" | "red" }) {
  const pct = Math.round(score * 100);
  const barColor = color === "blue" ? "bg-blue-500" : "bg-red-500";
  const textColor = color === "blue" ? "text-blue-700" : "text-red-600";
  return (
    <div className="flex-1">
      <div className="flex justify-between text-xs mb-1">
        <span className="text-gray-500">{label}</span>
        <span className={`font-bold ${textColor}`}>{pct}%</span>
      </div>
      <div className="h-2 bg-gray-100 rounded overflow-hidden">
        <div className={`h-full rounded transition-all ${barColor}`} style={{ width: `${pct}%` }} />
      </div>
      <p className="text-[10px] text-gray-400 mt-0.5">{sublabel}</p>
    </div>
  );
}

function OddsGrid() {
  return (
    <div className="grid grid-cols-3 gap-3 mb-4">
      {ODDS_LABELS.map((label, i) => {
        const delta = ODDS_CURRENTS[i] - ODDS_OPENS[i];
        const deltaColor = delta > 0.05 ? "text-red-500" : delta < -0.05 ? "text-green-600" : "text-gray-500";
        return (
          <div key={label} className={`border rounded-lg p-3 text-center ${BADGE[label]}`}>
            <p className="text-sm font-bold">{label}</p>
            <p className="text-xs opacity-60 mt-0.5">Açılış</p>
            <p className="text-lg font-extrabold">{ODDS_OPENS[i].toFixed(2)}</p>
            <p className={`text-xs font-semibold mt-1 ${deltaColor}`}>
              {delta > 0 ? "+" : ""}{delta.toFixed(2)} {delta > 0.05 ? "↑" : delta < -0.05 ? "↓" : "~"}
            </p>
            <p className="text-[10px] opacity-50 mt-0.5">Güncel: {ODDS_CURRENTS[i].toFixed(2)}</p>
          </div>
        );
      })}
    </div>
  );
}

function SharpMoneyRow() {
  const signal = DEMO.sharpSignal;
  const abs = Math.abs(signal);
  const toward = signal > 0 ? "Deplasman" : "Ev Sahibi";
  const color = signal > 0 ? "text-red-600" : "text-blue-700";
  const strength = abs > 0.7 ? "Güçlü" : "Orta";
  return (
    <div className="bg-gray-50 rounded-lg p-3 flex items-center justify-between">
      <div>
        <p className="text-xs font-semibold text-gray-600 mb-0.5">Sharp Money Sinyali</p>
        <span className={`text-xs font-semibold ${color}`}>
          {strength} → {toward} {signal > 0 ? "→" : "←"}
        </span>
      </div>
      <div className="text-right">
        <div className="w-24 h-2 bg-gray-200 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full ${signal > 0 ? "bg-red-500" : "bg-blue-500"}`}
            style={{ width: `${abs * 100}%`, marginLeft: signal > 0 ? "auto" : 0 }}
          />
        </div>
        <p className="text-[10px] text-gray-400 mt-0.5">← Ev · Dep →</p>
      </div>
    </div>
  );
}

function XGBars() {
  const sides = [
    { team: DEMO.home, value: DEMO.xg.home, barColor: "bg-blue-400", textColor: "text-blue-600" },
    { team: DEMO.away, value: DEMO.xg.away, barColor: "bg-red-400",  textColor: "text-red-500"  },
  ] as const;
  return (
    <div className="space-y-2">
      <p className="text-xs text-gray-400 mb-1">xG proxy (son 5 maç ortalaması)</p>
      {sides.map(({ team, value, barColor, textColor }) => (
        <div key={team} className="flex items-center gap-2">
          <span className={`text-[10px] font-bold px-1 rounded w-20 shrink-0 ${textColor}`}>{team.slice(0, 10)}</span>
          <div className="flex-1 h-3 bg-gray-100 rounded overflow-hidden">
            <div className={`h-full ${barColor} rounded`} style={{ width: `${Math.min(100, value * 50)}%` }} />
          </div>
          <span className="text-xs font-mono text-gray-600 w-10 text-right">{value.toFixed(2)}</span>
        </div>
      ))}
    </div>
  );
}

const H2H_PILL: Record<"W" | "D" | "L", string> = {
  W: "bg-green-100 text-green-800",
  D: "bg-amber-100 text-amber-800",
  L: "bg-red-100 text-red-800",
};
const H2H_LABEL: Record<"W" | "D" | "L", string> = { W: "G", D: "B", L: "M" };

function H2HPills() {
  const { h2h } = DEMO;
  const hw = Math.round(h2h.homeWinPct * 100);
  const dr = Math.round(h2h.drawPct * 100);
  const aw = Math.round(h2h.awayWinPct * 100);
  return (
    <div>
      <div className="flex gap-1.5 mb-3">
        {h2h.results.map((r, i) => (
          <span key={i} className={`text-xs font-bold px-2 py-0.5 rounded-full ${H2H_PILL[r]}`}>
            {H2H_LABEL[r]}
          </span>
        ))}
      </div>
      <div className="flex h-5 rounded overflow-hidden text-white text-[10px] font-bold">
        <div className="bg-blue-500 flex items-center justify-center" style={{ width: `${hw}%` }}>{hw}%</div>
        <div className="bg-amber-400 flex items-center justify-center" style={{ width: `${dr}%` }}>{dr}%</div>
        <div className="bg-red-500 flex items-center justify-center" style={{ width: `${aw}%` }}>{aw}%</div>
      </div>
      <div className="flex justify-between text-[10px] text-gray-400 mt-0.5">
        <span className="text-blue-600 font-medium">{DEMO.home}</span>
        <span>Beraberlik</span>
        <span className="text-red-500 font-medium">{DEMO.away}</span>
      </div>
    </div>
  );
}

// ── Main export ───────────────────────────────────────────────────────────────

export default function StaticMatchPreview() {
  const { motivation } = DEMO;
  return (
    <div className="mt-12">
      {/* Eyebrow divider */}
      <div className="flex items-center gap-3 mb-6">
        <div className="flex-1 h-px bg-gray-200" />
        <span className="text-xs font-semibold text-gray-400 uppercase tracking-widest whitespace-nowrap">
          Abone Önizleme
        </span>
        <div className="flex-1 h-px bg-gray-200" />
      </div>
      <div className="text-center mb-6">
        <h2 className="text-xl font-bold text-gray-800">Abonelerin gördüğü tam analiz sayfası</h2>
        <p className="mt-1 text-sm text-gray-500">Abone olduğunuzda her maç için bu analiz açılır.</p>
      </div>

      {/* Match card shell */}
      <div className="bg-white rounded-xl shadow-md border border-gray-100 overflow-hidden">
        {/* brand-900 header */}
        <div className="bg-brand-900 px-5 py-4 flex items-center justify-between">
          <div className="text-xs text-blue-300 leading-snug">
            {DEMO.week}<br />#{DEMO.seq}
          </div>
          <div className="text-center">
            <p className="text-white font-bold text-sm">{DEMO.home} — {DEMO.away}</p>
            <p className="text-blue-300 text-xs mt-0.5">{DEMO.kickoff}</p>
          </div>
          <div className="text-right text-xs text-blue-300 leading-snug">
            Derby<br /><span aria-hidden="true">🔴</span>
          </div>
        </div>

        <div className="p-5 space-y-4">
          <ProbBar />

          {/* Confidence + badge */}
          <div className="flex items-center gap-3 bg-gray-50 rounded-lg p-3">
            <ConfidenceRing score={DEMO.confidence} pick={DEMO.primary} size={52} />
            <div>
              <p className="text-xs text-gray-400">
                Güven <span className="ml-1 text-orange-500 text-[10px]">×0.75 derby</span>
              </p>
              <p className="text-xl font-black text-green-600">%{DEMO.confidence}</p>
            </div>
            <div className="ml-4">
              <p className="text-xs text-gray-400 mb-1">Öneri</p>
              <span className="text-sm font-bold px-3 py-1 rounded-full border bg-blue-100 text-blue-800 border-blue-200">
                {DEMO.primary} (Tekli)
              </span>
            </div>
          </div>

          {/* Reason pills */}
          <div className="flex flex-wrap gap-1.5">
            {DEMO.reasons.map((r) => (
              <span key={r} className="bg-blue-50 text-blue-700 text-xs px-2.5 py-0.5 rounded-full border border-blue-100">
                {r}
              </span>
            ))}
          </div>

          {/* Motivation */}
          <SectionHeader>Motivasyon &amp; Hedef</SectionHeader>
          <div className="flex gap-6">
            <MotivationGauge label={DEMO.home} score={motivation.home} sublabel={motivation.homeLabel} color="blue" />
            <MotivationGauge label={DEMO.away} score={motivation.away} sublabel={motivation.awayLabel} color="red" />
          </div>

          {/* Radar */}
          <SectionHeader>Takım Karşılaştırması</SectionHeader>
          <div className="flex justify-center">
            <RadarChart dimensions={DEMO.radarDims} homeTeam={DEMO.home} awayTeam={DEMO.away} size={240} />
          </div>

          {/* Odds */}
          <SectionHeader>Oran Hareketi &amp; Sharp Money</SectionHeader>
          <OddsGrid />
          <SharpMoneyRow />

          {/* xG */}
          <SectionHeader>xG Proxy &amp; Form Kalitesi</SectionHeader>
          <XGBars />

          {/* H2H */}
          <SectionHeader>Son Karşılaşmalar (H2H)</SectionHeader>
          <H2HPills />
        </div>
      </div>

      <p className="text-center text-xs text-gray-400 mt-3">
        Örnek veri · Abonelikte gerçek veriler açılır
      </p>
    </div>
  );
}
