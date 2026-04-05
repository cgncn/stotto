import { get, PoolMatch, PoolSummary } from "@/lib/api";
import MatchTable from "@/components/MatchTable";
import { SkeletonRow } from "@/components/Skeleton";

export const revalidate = 60;

async function getData(): Promise<{ pool: PoolSummary | null; matches: PoolMatch[]; fetchedAt: string }> {
  const fetchedAt = new Date().toISOString();
  try {
    const pool = await get<PoolSummary>("/weekly-pools/current");
    const matches = await get<PoolMatch[]>(`/weekly-pools/${pool.id}`);
    return { pool, matches, fetchedAt };
  } catch {
    return { pool: null, matches: [], fetchedAt };
  }
}

export default async function HomePage() {
  const { pool, matches, fetchedAt } = await getData();

  if (!pool) {
    return (
      <div className="text-center py-20 text-gray-500">
        <p className="text-2xl font-semibold mb-2">Aktif hafta bulunamadı</p>
        <p className="text-sm">Spor Toto havuzu henüz oluşturulmadı.</p>
        <p className="text-xs text-gray-400 mt-4">
          <a href="/admin" className="text-blue-500 hover:underline">Yönetim panelinden</a> hafta içe aktarabilirsiniz.
        </p>
      </div>
    );
  }

  return <MatchTable pool={pool} matches={matches} refreshedAt={fetchedAt} />;
}
