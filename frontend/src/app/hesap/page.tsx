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

interface PaymentHistoryItem {
  startDate?: string;
  endDate?: string;
  price?: number;
  currencyCode?: string;
  paymentStatus?: string;
  [key: string]: unknown;
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

const SUB_STATUS_LABELS: Record<string, string> = {
  active: "AKTİF",
  paused: "DURAKLATILDI",
  past_due: "ÖDEME GECİKMİŞ",
  cancelled: "İPTAL EDİLDİ",
  expired: "SÜRESİ DOLDU",
  inactive: "AKTİF DEĞİL",
};

const SUB_STATUS_COLORS: Record<string, string> = {
  active: "bg-green-100 text-green-700",
  paused: "bg-yellow-100 text-yellow-700",
  past_due: "bg-red-100 text-red-600",
  cancelled: "bg-gray-100 text-gray-500",
  expired: "bg-gray-100 text-gray-500",
  inactive: "bg-gray-100 text-gray-500",
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

  // Subscription section state
  const [subStatus, setSubStatus] = useState<string | null>(null);
  const [paymentHistory, setPaymentHistory] = useState<PaymentHistoryItem[]>([]);
  const [subActionLoading, setSubActionLoading] = useState(false);
  const [cancelConfirm, setCancelConfirm] = useState(false);
  const [subError, setSubError] = useState<string | null>(null);

  const isSubscriber = user?.role === "SUBSCRIBER" || user?.role === "ADMIN";

  useEffect(() => {
    if (!authLoading && !token) {
      router.push("/auth/giris");
    }
  }, [authLoading, token, router]);

  // Sync local subStatus with user profile
  useEffect(() => {
    if (user?.subscription_status) {
      setSubStatus(user.subscription_status);
    }
  }, [user?.subscription_status]);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    async function fetchData() {
      setDataLoading(true);
      try {
        const requests: Promise<unknown>[] = [
          authedGet<SavedCoupon[]>("/users/me/coupons", token!),
          authedGet<UserStats>("/users/me/stats", token!),
        ];
        if (isSubscriber) {
          requests.push(
            authedGet<{ items: PaymentHistoryItem[] }>("/subscriptions/history", token!)
          );
        }
        const results = await Promise.allSettled(requests);
        if (cancelled) return;
        if (results[0].status === "fulfilled")
          setCoupons(results[0].value as SavedCoupon[]);
        if (results[1].status === "fulfilled")
          setStats(results[1].value as UserStats);
        if (results[2]?.status === "fulfilled") {
          const histRes = results[2].value as { items: PaymentHistoryItem[] };
          setPaymentHistory(histRes.items ?? []);
        }
      } finally {
        if (!cancelled) setDataLoading(false);
      }
    }
    fetchData();
    return () => {
      cancelled = true;
    };
  }, [token, isSubscriber]);

  async function handleLogout() {
    logout();
    router.push("/");
  }

  async function handlePauseResume() {
    if (!token) return;
    setSubError(null);
    setSubActionLoading(true);
    try {
      const isPaused = subStatus === "paused";
      const endpoint = isPaused ? "/subscriptions/resume" : "/subscriptions/pause";
      const res = await authedPost<{ subscription_status: string }>(endpoint, {}, token);
      setSubStatus(res.subscription_status);
    } catch {
      setSubError("İşlem gerçekleştirilemedi. Lütfen tekrar deneyin.");
    } finally {
      setSubActionLoading(false);
    }
  }

  async function handleCancel() {
    if (!token) return;
    setSubError(null);
    setSubActionLoading(true);
    try {
      await authedPost("/subscriptions/cancel", {}, token);
      logout();
      router.push("/?cancelled=1");
    } catch {
      setSubActionLoading(false);
      setSubError("Abonelik iptal edilemedi. Lütfen tekrar deneyin.");
    }
  }

  async function handleCardUpdate() {
    if (!token) return;
    setSubError(null);
    setSubActionLoading(true);
    try {
      const res = await authedPost<{ url: string }>("/subscriptions/update-card", {}, token);
      window.location.href = res.url;
    } catch {
      setSubActionLoading(false);
      setSubError("Kart güncelleme sayfasına yönlendirilemedi.");
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
  const subStatusLabel = SUB_STATUS_LABELS[subStatus ?? ""] ?? subStatus ?? "";
  const subStatusColor =
    SUB_STATUS_COLORS[subStatus ?? ""] ?? "bg-gray-100 text-gray-500";
  const isPaused = subStatus === "paused";

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* ── Profile card ─────────────────────────────────────────── */}
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
          <span
            className={`text-xs font-semibold px-2.5 py-1 rounded-full ${roleColor}`}
          >
            {roleLabel}
          </span>
        </div>
        <div className="flex flex-wrap gap-3 mt-4">
          <button
            onClick={handleLogout}
            className="text-sm px-4 py-2 rounded-lg border border-gray-200 text-gray-600 hover:text-red-600 hover:border-red-300 transition-colors"
          >
            Çıkış Yap
          </button>
        </div>
      </div>

      {/* ── Abonelik section (subscribers only) ──────────────────── */}
      {isSubscriber ? (
        <div id="abonelik" className="bg-white rounded-xl shadow-md p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-700">Abonelik</h2>
            {subStatus && (
              <span
                className={`text-xs font-semibold px-2.5 py-1 rounded-full ${subStatusColor}`}
              >
                {subStatusLabel}
              </span>
            )}
          </div>

          {user.subscription_expires_at && (
            <p className="text-sm text-gray-600 mb-4">
              Yenileme:{" "}
              <span className="font-medium">
                {formatTurkishDate(user.subscription_expires_at)}
              </span>
            </p>
          )}

          {subError && (
            <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2 mb-3">
              {subError}
            </p>
          )}

          {/* Action buttons */}
          {!cancelConfirm ? (
            <div className="flex flex-wrap gap-3 mb-6">
              <button
                onClick={handleCardUpdate}
                disabled={subActionLoading}
                className="text-sm px-4 py-2 rounded-lg border border-gray-200 text-gray-700 hover:border-brand-400 hover:text-brand-700 disabled:opacity-50 transition-colors"
              >
                Kartı Güncelle
              </button>
              <button
                onClick={handlePauseResume}
                disabled={subActionLoading}
                className="text-sm px-4 py-2 rounded-lg border border-gray-200 text-gray-700 hover:border-yellow-400 hover:text-yellow-700 disabled:opacity-50 transition-colors"
              >
                {subActionLoading
                  ? "İşleniyor…"
                  : isPaused
                  ? "Devam Et"
                  : "Duraklat"}
              </button>
              <button
                onClick={() => setCancelConfirm(true)}
                disabled={subActionLoading}
                className="text-sm px-4 py-2 rounded-lg border border-gray-200 text-red-500 hover:border-red-300 hover:text-red-700 disabled:opacity-50 transition-colors"
              >
                İptal Et
              </button>
            </div>
          ) : (
            /* Cancel confirmation */
            <div className="flex flex-wrap items-center gap-3 mb-6 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
              <p className="text-sm text-red-700 font-medium">
                Aboneliğinizi iptal etmek istediğinizden emin misiniz?
              </p>
              <div className="flex gap-2">
                <button
                  onClick={handleCancel}
                  disabled={subActionLoading}
                  className="text-sm px-3 py-1.5 rounded-lg bg-red-600 text-white hover:bg-red-700 disabled:opacity-50 transition-colors"
                >
                  {subActionLoading ? "İşleniyor…" : "Evet, İptal Et"}
                </button>
                <button
                  onClick={() => setCancelConfirm(false)}
                  disabled={subActionLoading}
                  className="text-sm px-3 py-1.5 rounded-lg border border-gray-200 text-gray-600 hover:border-gray-400 transition-colors"
                >
                  Vazgeç
                </button>
              </div>
            </div>
          )}

          {/* Payment history */}
          <div>
            <h3 className="text-sm font-semibold text-gray-600 mb-3">
              Ödeme Geçmişi
            </h3>
            {paymentHistory.length === 0 ? (
              <p className="text-sm text-gray-400">Henüz ödeme geçmişi yok.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-100 text-left text-xs text-gray-500 uppercase tracking-wide">
                      <th className="pb-2 pr-4">Tarih</th>
                      <th className="pb-2 pr-4 text-right">Tutar</th>
                      <th className="pb-2 text-right">Durum</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {paymentHistory.map((item, idx) => (
                      <tr key={idx} className="hover:bg-gray-50">
                        <td className="py-2 pr-4 text-gray-700">
                          {item.startDate
                            ? formatTurkishDate(item.startDate)
                            : "—"}
                        </td>
                        <td className="py-2 pr-4 text-right text-gray-700">
                          {item.price != null
                            ? `${item.price} ${item.currencyCode ?? "TRY"}`
                            : "—"}
                        </td>
                        <td className="py-2 text-right text-gray-700">
                          {(item.paymentStatus as string) ?? "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      ) : (
        /* FREE user — upgrade prompt */
        <div className="bg-white rounded-xl shadow-md p-6 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-700 mb-1">Abonelik</h2>
            <p className="text-sm text-gray-500">
              Gelişmiş analizlere erişmek için abone olun.
            </p>
          </div>
          <Link
            href="/uye-ol"
            className="bg-brand-600 text-white text-sm px-4 py-2 rounded-lg hover:bg-brand-700 transition-colors whitespace-nowrap"
          >
            Abone Ol →
          </Link>
        </div>
      )}

      {/* ── Stats ────────────────────────────────────────────────── */}
      {stats && (
        <div className="bg-white rounded-xl shadow-md p-6">
          <h2 className="text-lg font-semibold text-gray-700 mb-3">
            İstatistikler
          </h2>
          <div className="flex gap-6">
            <div>
              <p className="text-2xl font-bold text-gray-800">
                {stats.total_coupons}
              </p>
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

      {/* ── Saved coupons ─────────────────────────────────────────── */}
      <div className="bg-white rounded-xl shadow-md p-6">
        <h2 className="text-lg font-semibold text-gray-700 mb-4">
          Kayıtlı Kuponlar
        </h2>
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
                  <tr
                    key={`${c.week_code}-${c.scenario_type}`}
                    className="hover:bg-gray-50"
                  >
                    <td className="py-2 pr-4 text-gray-700">{c.week_code}</td>
                    <td className="py-2 pr-4 text-gray-700 capitalize">
                      {c.scenario_type}
                    </td>
                    <td className="py-2 pr-4 text-right text-gray-700">
                      {c.total_columns}
                    </td>
                    <td className="py-2 pr-4 text-right text-gray-700">
                      {c.correct_count ?? "—"}
                    </td>
                    <td className="py-2 text-right text-gray-700">
                      {c.brier_score != null
                        ? c.brier_score.toFixed(3)
                        : "—"}
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
