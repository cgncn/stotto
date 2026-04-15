interface Props {
  score: number | null | undefined; // 0–100
  pick: string;
  size?: number;
}

const PICK_COLORS: Record<string, { stroke: string; text: string }> = {
  "1":   { stroke: "#3b82f6", text: "#1d4ed8" },
  "X":   { stroke: "#f59e0b", text: "#92400e" },
  "2":   { stroke: "#ef4444", text: "#991b1b" },
  "1X":  { stroke: "#8b5cf6", text: "#5b21b6" },
  "X2":  { stroke: "#f97316", text: "#9a3412" },
  "12":  { stroke: "#10b981", text: "#065f46" },
  "1X2": { stroke: "#6b7280", text: "#111827" },
};

// Spor Toto realistic range: 15 (worst) → 80 (best)
// We map this to visual 0–100% fill so even "low" scores show meaningful arc
const MIN_SCORE = 15;
const MAX_SCORE = 80;

function confidenceLabel(score: number): { label: string; color: string } {
  if (score >= 60) return { label: "Yüksek", color: "#16a34a" };
  if (score >= 38) return { label: "Orta",   color: "#d97706" };
  return                  { label: "Düşük",  color: "#dc2626" };
}

export default function ConfidenceRing({ score, pick, size = 52 }: Props) {
  const colors = PICK_COLORS[pick] ?? PICK_COLORS["X"];
  const radius = (size - 6) / 2;
  const circumference = 2 * Math.PI * radius;

  // Normalize to visual fill: 15→0%, 80→100%
  const normalised = score == null
    ? 0
    : Math.max(0, Math.min(100, ((score - MIN_SCORE) / (MAX_SCORE - MIN_SCORE)) * 100));

  const dash = (normalised / 100) * circumference;
  const center = size / 2;
  const fontSize = size < 44 ? 9 : 10;
  const pickSize = size < 44 ? 12 : 14;

  const label = score != null ? confidenceLabel(score) : null;

  // Arc color: override pick color with quality color when high/low
  const arcColor = score == null
    ? "#d1d5db"
    : score >= 60 ? "#16a34a"
    : score >= 38 ? colors.stroke
    : "#f87171";

  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
        {/* Background track */}
        <circle cx={center} cy={center} r={radius} fill="none" stroke="#e5e7eb" strokeWidth={5} />
        {/* Progress arc */}
        <circle
          cx={center} cy={center} r={radius}
          fill="none"
          stroke={arcColor}
          strokeWidth={5}
          strokeDasharray={`${dash} ${circumference}`}
          strokeLinecap="round"
          style={{ transition: "stroke-dasharray 0.4s ease" }}
        />
      </svg>
      {/* Center text */}
      <div className="absolute flex flex-col items-center justify-center leading-none text-center">
        <span style={{ fontSize: pickSize, fontWeight: 800, color: colors.text, lineHeight: 1 }}>
          {pick}
        </span>
        {label && (
          <span style={{ fontSize, color: label.color, lineHeight: 1.3, fontWeight: 600 }}>
            {label.label}
          </span>
        )}
      </div>
    </div>
  );
}
