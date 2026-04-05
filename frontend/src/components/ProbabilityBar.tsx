"use client";

interface Props {
  p1: number;
  px: number;
  p2: number;
  primaryPick: string;
}

const PICK_COLOR: Record<string, string> = {
  "1": "bg-blue-500",
  X: "bg-amber-400",
  "2": "bg-red-500",
};

export default function ProbabilityBar({ p1, px, p2, primaryPick }: Props) {
  const pcts = [
    { label: "1", value: p1 },
    { label: "X", value: px },
    { label: "2", value: p2 },
  ];

  return (
    <div className="w-full">
      <div className="flex rounded overflow-hidden h-2 w-full">
        {pcts.map(({ label, value }) => (
          <div
            key={label}
            style={{ width: `${(value * 100).toFixed(1)}%` }}
            className={`${PICK_COLOR[label]} transition-all`}
            title={`${label}: ${(value * 100).toFixed(0)}%`}
          />
        ))}
      </div>
      <div className="flex justify-between text-xs text-gray-500 mt-0.5">
        {pcts.map(({ label, value }) => (
          <span
            key={label}
            className={label === primaryPick ? "font-bold text-gray-800" : ""}
          >
            {label} {(value * 100).toFixed(0)}%
          </span>
        ))}
      </div>
    </div>
  );
}
