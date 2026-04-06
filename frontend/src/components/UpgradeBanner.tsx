import Link from "next/link";

export function UpgradeBanner() {
  return (
    <div className="rounded-lg border border-dashed border-gray-600 bg-gray-800/50 p-6 text-center">
      <p className="text-gray-400 text-sm mb-3">
        Bu özellik Abone planı gerektirir.
      </p>
      <Link
        href="/uye-ol"
        className="inline-block rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 transition-colors"
      >
        Üye Ol →
      </Link>
    </div>
  );
}
