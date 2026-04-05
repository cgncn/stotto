interface Props {
  score: number | null | undefined; // 0–100
  pick: string;
  size?: number;
}

const PICK_COLORS: Record<string, { stroke: string; text: string; bg: string }> = {
  "1":   { stroke: "#3b82f6", text: "#1d4ed8", bg: "#eff6ff" },
  "X":   { stroke: "#f59e0b", text: "#92400e", bg: "#fffbeb" },
  "2":   { stroke: "#ef4444", text: "#991b1b", bg: "#fef2f2" },
  "1X":  { stroke: "#8b5cf6", text: "#5b21b6", bg: "#f5f3ff" },
  "X2":  { stroke: "#f97316", text: "#9a3412", bg: "#fff7ed" },
  "12":  { stroke: "#10b981", text: "#065f46", bg: "#ecfdf5" },
  "1X2": { stroke: "#6b7280", text: "#111827", bg: "#f9fafb" },
};

export default function ConfidenceRing({ score, pick, size = 52 }: Props) {
  const colors = PICK_COLORS[pick] ?? PICK_COLORS["X"];
  const radius = (size - 6) / 2;
  const circumference = 2 * Math.PI * radius;
  const pct = Math.max(0, Math.min(100, score ?? 0));
  const dash = (pct / 100) * circumference;
  const center = size / 2;
  const fontSize = size < 44 ? 9 : 11;
  const pickSize = size < 44 ? 13 : 15;

  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
        {/* Background track */}
        <circle cx={center} cy={center} r={radius} fill="none" stroke="#e5e7eb" strokeWidth={5} />
        {/* Progress arc */}
        <circle
          cx={center} cy={center} r={radius}
          fill="none"
          stroke={score == null ? "#d1d5db" : colors.stroke}
          strokeWidth={5}
          strokeDasharray={`${dash} ${circumference}`}
          strokeLinecap="round"
          style={{ transition: "stroke-dasharray 0.4s ease" }}
        />
      </svg>
      {/* Center text */}
      <div
        className="absolute flex flex-col items-center justify-center leading-none"
        style={{ transform: "none" }}
      >
        <span style={{ fontSize: pickSize, fontWeight: 800, color: colors.text, lineHeight: 1 }}>
          {pick}
        </span>
        {score != null && (
          <span style={{ fontSize, color: "#6b7280", lineHeight: 1.2 }}>
            {pct.toFixed(0)}
          </span>
        )}
      </div>
    </div>
  );
}
