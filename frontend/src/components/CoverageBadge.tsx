const STYLE: Record<string, string> = {
  single: "bg-green-100 text-green-800",
  double: "bg-yellow-100 text-yellow-800",
  triple: "bg-red-100 text-red-800",
};

const LABEL: Record<string, string> = {
  single: "Tekli",
  double: "İkili",
  triple: "Üçlü",
};

interface Props {
  coveragePick: string;
  coverageType: string;
}

export default function CoverageBadge({ coveragePick, coverageType }: Props) {
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold ${STYLE[coverageType] ?? "bg-gray-100 text-gray-700"}`}
    >
      {coveragePick}
      <span className="opacity-60">({LABEL[coverageType] ?? coverageType})</span>
    </span>
  );
}
