"use client";

interface RadarDimension {
  label: string;
  home: number; // 0–1
  away: number; // 0–1
}

interface Props {
  dimensions: RadarDimension[];
  homeTeam: string;
  awayTeam: string;
  size?: number;
}

function polarToXY(angle: number, r: number, cx: number, cy: number) {
  const rad = ((angle - 90) * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

export default function RadarChart({ dimensions, homeTeam, awayTeam, size = 260 }: Props) {
  const n = dimensions.length;
  if (n < 3) return null;

  const cx = size / 2;
  const cy = size / 2;
  const maxR = size * 0.36;
  const labelR = size * 0.46;
  const rings = [0.25, 0.5, 0.75, 1.0];
  const angleStep = 360 / n;

  // Build polygon points string from values
  function buildPolygon(values: number[]) {
    return values
      .map((v, i) => {
        const angle = i * angleStep;
        const r = Math.max(0, Math.min(1, v)) * maxR;
        const pt = polarToXY(angle, r, cx, cy);
        return `${pt.x},${pt.y}`;
      })
      .join(" ");
  }

  const homePoly = buildPolygon(dimensions.map((d) => d.home));
  const awayPoly = buildPolygon(dimensions.map((d) => d.away));

  return (
    <div>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="overflow-visible">
        {/* Grid rings */}
        {rings.map((r) => {
          const pts = Array.from({ length: n }, (_, i) => {
            const angle = i * angleStep;
            const pt = polarToXY(angle, r * maxR, cx, cy);
            return `${pt.x},${pt.y}`;
          }).join(" ");
          return (
            <polygon
              key={r}
              points={pts}
              fill="none"
              stroke="#e5e7eb"
              strokeWidth={1}
            />
          );
        })}

        {/* Axis lines */}
        {dimensions.map((_, i) => {
          const angle = i * angleStep;
          const outer = polarToXY(angle, maxR, cx, cy);
          return (
            <line
              key={i}
              x1={cx} y1={cy}
              x2={outer.x} y2={outer.y}
              stroke="#e5e7eb" strokeWidth={1}
            />
          );
        })}

        {/* Away polygon */}
        <polygon
          points={awayPoly}
          fill="rgba(239,68,68,0.12)"
          stroke="#ef4444"
          strokeWidth={2}
          strokeLinejoin="round"
        />

        {/* Home polygon */}
        <polygon
          points={homePoly}
          fill="rgba(59,130,246,0.15)"
          stroke="#3b82f6"
          strokeWidth={2}
          strokeLinejoin="round"
        />

        {/* Dots */}
        {dimensions.map((d, i) => {
          const angle = i * angleStep;
          const hp = polarToXY(angle, d.home * maxR, cx, cy);
          const ap = polarToXY(angle, d.away * maxR, cx, cy);
          return (
            <g key={i}>
              <circle cx={ap.x} cy={ap.y} r={3} fill="#ef4444" />
              <circle cx={hp.x} cy={hp.y} r={3} fill="#3b82f6" />
            </g>
          );
        })}

        {/* Labels */}
        {dimensions.map((d, i) => {
          const angle = i * angleStep;
          const pt = polarToXY(angle, labelR, cx, cy);
          const anchor =
            pt.x < cx - 4 ? "end" : pt.x > cx + 4 ? "start" : "middle";
          return (
            <text
              key={i}
              x={pt.x}
              y={pt.y}
              textAnchor={anchor}
              dominantBaseline="middle"
              fontSize={10}
              fill="#6b7280"
              fontFamily="sans-serif"
            >
              {d.label}
            </text>
          );
        })}
      </svg>

      {/* Legend */}
      <div className="flex justify-center gap-6 mt-1 text-xs text-gray-500">
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-0.5 bg-blue-500 rounded" />
          {homeTeam}
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-0.5 bg-red-500 rounded" />
          {awayTeam}
        </span>
      </div>
    </div>
  );
}
