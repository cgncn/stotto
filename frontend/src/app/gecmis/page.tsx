import Link from "next/link";
import { get } from "@/lib/api";
import PoolHistoryCard from "./PoolHistoryCard";

export const revalidate = 300;

interface PoolAccuracySummary {
  id: number;
  week_code: string;
  created_at: string;
  match_count: number;
  scored_count: number;
  correct_count: number;
  brier_score: number | null;
  avg_confidence: number | null;
}

interface MatchResultRow {
  sequence_no: number;
  home_team: string;
  away_team: string;
  kickoff_at: string | null;
  result: string | null;
  home_score: number | null;
  away_score: number | null;
  primary_pick: string | null;
  p1: number | null;
  px: number | null;
  p2: number | null;
  confidence_score: number | null;
  correct: boolean | null;
}

async function getHistory(): Promise<PoolAccuracySummary[]> {
  try {
    return await get<PoolAccuracySummary[]>("/weekly-pools/history");
  } catch {
    return [];
  }
}

async function getPoolResults(poolId: number): Promise<MatchResultRow[]> {
  try {
    return await get<MatchResultRow[]>(`/weekly-pools/${poolId}/results`);
  } catch {
    return [];
  }
}

export default async function GecmisPage() {
  const pools = await getHistory();

  const poolsWithRows = await Promise.all(
    pools.map(async (pool) => ({
      pool,
      rows: await getPoolResults(pool.id),
    }))
  );

  return (
    <div className="bg-zinc-950 min-h-screen text-white">
      {/* Header */}
      <nav className="border-b border-zinc-800 bg-zinc-900">
        <div className="max-w-4xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link href="/" className="text-xl font-bold tracking-tight hover:opacity-80">
              STOTTO
            </Link>
            <span className="text-zinc-600">|</span>
            <span className="text-sm text-zinc-400 font-medium">Geçmiş Haftalar</span>
          </div>
          <Link
            href="/"
            className="text-xs text-zinc-400 hover:text-white transition-colors flex items-center gap-1"
          >
            Ana Sayfa →
          </Link>
        </div>
      </nav>

      <div className="max-w-4xl mx-auto px-4 py-8">
        {poolsWithRows.length === 0 ? (
          <div className="text-center py-20 text-zinc-600">
            <p className="text-lg font-medium">Henüz kapanmış hafta yok</p>
            <p className="text-sm mt-2">Settled haftalar burada görünecek.</p>
          </div>
        ) : (
          <div className="space-y-4">
            {poolsWithRows.map(({ pool, rows }) => (
              <PoolHistoryCard key={pool.id} pool={pool} rows={rows} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
