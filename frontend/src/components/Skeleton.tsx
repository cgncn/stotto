export function SkeletonRow() {
  return (
    <div className="animate-pulse flex items-center gap-3 px-4 py-3 border-b border-gray-100">
      <div className="w-6 h-4 bg-gray-200 rounded" />
      <div className="flex-1 space-y-1.5">
        <div className="h-4 bg-gray-200 rounded w-1/3" />
        <div className="h-3 bg-gray-100 rounded w-1/4" />
      </div>
      <div className="w-16 h-5 bg-gray-200 rounded-full" />
      <div className="w-10 h-10 bg-gray-200 rounded-full" />
    </div>
  );
}

export function SkeletonCard() {
  return (
    <div className="animate-pulse bg-white rounded-xl shadow p-5 space-y-3">
      <div className="h-4 bg-gray-200 rounded w-1/4" />
      <div className="h-6 bg-gray-200 rounded w-2/3" />
      <div className="h-4 bg-gray-100 rounded w-full" />
      <div className="h-4 bg-gray-100 rounded w-5/6" />
    </div>
  );
}

export function SkeletonBlock({ lines = 3 }: { lines?: number }) {
  return (
    <div className="animate-pulse space-y-2">
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className={`h-3 bg-gray-200 rounded ${i === lines - 1 ? "w-4/5" : "w-full"}`} />
      ))}
    </div>
  );
}
