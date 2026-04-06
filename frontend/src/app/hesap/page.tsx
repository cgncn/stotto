"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { authedGet, authedPost } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

interface SavedCoupon {
  week_code: string;
  scenario_type: string;
  total_columns: number;
  correct_count: number | null;
  brier_score: number | null;
}

interface UserStats {
  total_coupons: number;
  avg_correct: number | null;
}

const ROLE_LABELS: Record<string, string> = {
  FREE: "ÜCRETSİZ",
  SUBSCRIBER: "ABONE",
  ADMIN: "ADMİN",
};

const ROLE_COLORS: Record<string, string> = {
  FREE: "bg-gray-100 text-gray-600",
  SUBSCRIBER: "bg-green-100 text-green-700",
  ADMIN: "bg-brand-100 text-brand-700",
};

function formatTurkishDate(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleDateString("tr-TR", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

export default function HesapPage() {
  const { user, token, logout, loading: authLoading } = useAuth();
  const router = useRouter();
  const [coupons, setCoupons] = useState<SavedCoupon[]>([]);
  const [stats, setStats] = useState<UserStats | null>(null);
  const [dataLoading, setDataLoading] = useState(true);
  const [portalLoading, setPortalLoading] = useState(false);
  const [portalError, setPortalError] = useState<string | null>(null);

  useEffect(() => {
    if (!authLoading && !token) {
      router.push("/auth/giris");
    }
  }, [authLoading, token, router]);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    async function fetchData() {
      setDataLoading(true);
      try {
        const [couponsData, statsData] = await Promise.allSettled([
          authedGet<SavedCoupon[]>("/users/me/coupons", token!),
          authedGet<UserStats>("/users/me/stats", token!),
        ]);
        if (cancelled) return;
        if (couponsData.status === "fulfilled") setCoupons(couponsData.value);
        if (statsData.status === "fulfilled") setStats(statsData.value);
      } finally {
        if (!cancelled) setDataLoading(false);
      }
    }
    fetchData();
    return () => { cancelled = true; };
  }, [token]);

  async function handleLogout() {
    logout();
    router.push("/");
  }

  async function handlePortal() {
    if (!token) return;
    setPortalError(null);
    setPortalLoading(true);
    try {
      const res = await authedPost<{ url: string }>("/subscriptions/portal", {}, token);
      window.location.href = res.url;
    } catch {
      setPortalLoading(false);
      setPortalError("Abonelik yönetim sayfasına yönlendirilemedi. Lütfen tekrar deneyin.");
    }
  }

  if (authLoading) {
    return (
      <div className="max-w-2xl mx-auto mt-10 space-y-4 animate-pulse">
        <div className="h-32 bg-gray-200 rounded-xl" />
        <div className="h-48 bg-gray-200 rounded-xl" />
      </div>
    );
  }

  if (!user) return null;

  const roleLabel = ROLE_LABELS[user.role] ?? user.role;
  const roleColor = ROLE_COLORS[user.role] ?? "bg-gray-100 text-gray-600";
  const isSubscriber = user.role === "SUBSCRIBER" || user.role === "ADMIN";

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* Profile card */}
      <div className="bg-white rounded-xl shadow-md p-6">
        <div className="flex items-start justify-between mb-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-800">
              {user.display_name ?? user.email}
            </h1>
            {user.display_name && (
              <p className="text-sm text-gray-500 mt-0.5">{user.email}</p>
            )}
          </div>
          <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${roleColor}`}>
            {roleLabel}
          </span>
        </div>

        {user.subscription_status && (
          <p className="text-sm text-gray-600 mb-1">
            Abonelik durumu:{" "}
            <span className="font-medium">{user.subscription_status}</span>
          </p>
        )}
        {user.subscription_expires_at && (
          <p className="text-sm text-gray-600 mb-4">
            Abonelik bitiş:{" "}
            <span className="font-medium">{formatTurkishDate(user.subscription_expires_at)}</span>
          </p>
        )}

        {portalError && (
          <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2 mb-2">
            {portalError}
          </p>
        )}
        <div className="flex flex-wrap gap-3 mt-4">
          {isSubscriber ? (
            <button
              onClick={handlePortal}
              disabled={portalLoading}
              className="bg-brand-600 text-white text-sm px-4 py-2 rounded-lg hover:bg-brand-700 disabled:opacity-50 transition-colors"
            >
              {portalLoading ? "Yönlendiriliyor…" : "Aboneliği Yönet"}
            </button>
          ) : (
            <Link
              href="/uye-ol"
              className="bg-brand-600 text-white text-sm px-4 py-2 rounded-lg hover:bg-brand-700 transition-colors"
            >
              Abone Ol
            </Link>
          )}
          <button
            onClick={handleLogout}
            className="text-sm px-4 py-2 rounded-lg border border-gray-200 text-gray-600 hover:text-red-600 hover:border-red-300 transition-colors"
          >
            Çıkış Yap
          </button>
        </div>
      </div>

      {/* Stats */}
      {stats && (
        <div className="bg-white rounded-xl shadow-md p-6">
          <h2 className="text-lg font-semibold text-gray-700 mb-3">İstatistikler</h2>
          <div className="flex gap-6">
            <div>
              <p className="text-2xl font-bold text-gray-800">{stats.total_coupons}</p>
              <p className="text-xs text-gray-500 mt-0.5">Toplam Kupon</p>
            </div>
            {stats.avg_correct != null && (
              <div>
                <p className="text-2xl font-bold text-gray-800">
                  {stats.avg_correct.toFixed(1)}
                </p>
                <p className="text-xs text-gray-500 mt-0.5">Ort. Doğru</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Saved coupons */}
      <div className="bg-white rounded-xl shadow-md p-6">
        <h2 className="text-lg font-semibold text-gray-700 mb-4">Kayıtlı Kuponlar</h2>
        {dataLoading ? (
          <div className="animate-pulse space-y-2">
            <div className="h-8 bg-gray-100 rounded" />
            <div className="h-8 bg-gray-100 rounded" />
          </div>
        ) : coupons.length === 0 ? (
          <p className="text-sm text-gray-400">Henüz kaydedilmiş kupon yok.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 text-left text-xs text-gray-500 uppercase tracking-wide">
                  <th className="pb-2 pr-4">Hafta</th>
                  <th className="pb-2 pr-4">Senaryo</th>
                  <th className="pb-2 pr-4 text-right">Kolon</th>
                  <th className="pb-2 pr-4 text-right">Doğru</th>
                  <th className="pb-2 text-right">Brier</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {coupons.map((c) => (
                  <tr key={`${c.week_code}-${c.scenario_type}`} className="hover:bg-gray-50">
                    <td className="py-2 pr-4 text-gray-700">{c.week_code}</td>
                    <td className="py-2 pr-4 text-gray-700 capitalize">{c.scenario_type}</td>
                    <td className="py-2 pr-4 text-right text-gray-700">{c.total_columns}</td>
                    <td className="py-2 pr-4 text-right text-gray-700">
                      {c.correct_count ?? "—"}
                    </td>
                    <td className="py-2 text-right text-gray-700">
                      {c.brier_score != null ? c.brier_score.toFixed(3) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
