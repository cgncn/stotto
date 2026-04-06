"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { authedPost } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

const FREE_FEATURES = [
  { label: "Haftalık maç listesi", available: true },
  { label: "Temel tahminler (1/X/2)", available: true },
  { label: "Birincil öneri", available: true },
  { label: "Radar grafik & takım analizleri", available: false },
  { label: "Bahis oranları hareketleri", available: false },
  { label: "Kupon senaryoları (güvenli/dengeli/agresif)", available: false },
  { label: "Kupon optimizasyonu", available: false },
  { label: "Kupon performans takibi", available: false },
];

const ABONE_FEATURES = FREE_FEATURES.map((f) => ({ ...f, available: true }));

function FeatureRow({ label, available }: { label: string; available: boolean }) {
  return (
    <li className="flex items-center gap-2 text-sm">
      {available ? (
        <span className="text-green-500 font-bold">✓</span>
      ) : (
        <span className="text-gray-300 font-bold">✗</span>
      )}
      <span className={available ? "text-gray-700" : "text-gray-400"}>{label}</span>
    </li>
  );
}

export default function UyeOlPage() {
  const { user, token, isSubscriber } = useAuth();
  const router = useRouter();
  const [checkoutLoading, setCheckoutLoading] = useState(false);
  const [portalLoading, setPortalLoading] = useState(false);

  async function handleCheckout() {
    if (!token) {
      router.push("/auth/giris?next=/uye-ol");
      return;
    }
    setCheckoutLoading(true);
    try {
      const res = await authedPost<{ url: string }>("/subscriptions/checkout", {}, token);
      window.location.href = res.url;
    } catch {
      setCheckoutLoading(false);
    }
  }

  async function handlePortal() {
    if (!token) return;
    setPortalLoading(true);
    try {
      const res = await authedPost<{ url: string }>("/subscriptions/portal", {}, token);
      window.location.href = res.url;
    } catch {
      setPortalLoading(false);
    }
  }

  return (
    <div className="max-w-3xl mx-auto">
      <div className="text-center mb-8">
        <h1 className="text-3xl font-bold text-gray-800">Üye Ol</h1>
        <p className="mt-2 text-gray-500">
          Gelişmiş analizlere ve kupon optimizasyonuna erişin.
        </p>
      </div>

      {/* Plan comparison */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
        {/* FREE */}
        <div className="bg-white rounded-xl shadow-md p-6 border border-gray-100">
          <div className="mb-4">
            <span className="inline-block text-xs font-semibold bg-gray-100 text-gray-500 px-2.5 py-1 rounded-full uppercase tracking-wide">
              Ücretsiz
            </span>
            <p className="mt-2 text-2xl font-bold text-gray-800">₺0</p>
            <p className="text-xs text-gray-400">sonsuza dek ücretsiz</p>
          </div>
          <ul className="space-y-2">
            {FREE_FEATURES.map((f) => (
              <FeatureRow key={f.label} {...f} />
            ))}
          </ul>
        </div>

        {/* ABONE */}
        <div className="bg-brand-900 rounded-xl shadow-md p-6 border border-brand-700 relative overflow-hidden">
          <div className="absolute top-3 right-3 bg-amber-400 text-amber-900 text-xs font-bold px-2 py-0.5 rounded-full">
            Önerilen
          </div>
          <div className="mb-4">
            <span className="inline-block text-xs font-semibold bg-brand-700 text-white px-2.5 py-1 rounded-full uppercase tracking-wide">
              Abone
            </span>
            <p className="mt-2 text-2xl font-bold text-white">Aylık Plan</p>
            <p className="text-xs text-brand-300">tüm özellikler dahil</p>
          </div>
          <ul className="space-y-2">
            {ABONE_FEATURES.map((f) => (
              <li key={f.label} className="flex items-center gap-2 text-sm">
                <span className="text-green-400 font-bold">✓</span>
                <span className="text-white">{f.label}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* CTA */}
      <div className="text-center">
        {isSubscriber ? (
          <div className="bg-green-50 border border-green-200 rounded-xl p-6">
            <p className="text-green-700 font-medium mb-3">
              Zaten aboneniz! Hesabı yönetmek için:
            </p>
            <button
              onClick={handlePortal}
              disabled={portalLoading}
              className="bg-brand-600 text-white px-6 py-2.5 rounded-lg text-sm font-medium hover:bg-brand-700 disabled:opacity-50 transition-colors"
            >
              {portalLoading ? "Yönlendiriliyor…" : "Aboneliği Yönet"}
            </button>
          </div>
        ) : (
          <div>
            <button
              onClick={handleCheckout}
              disabled={checkoutLoading}
              className="bg-brand-600 text-white px-8 py-3 rounded-xl text-base font-semibold hover:bg-brand-700 disabled:opacity-50 transition-colors shadow-lg"
            >
              {checkoutLoading ? "Yönlendiriliyor…" : "Abone Ol"}
            </button>
            {!user && (
              <p className="mt-3 text-sm text-gray-400">
                Devam etmek için{" "}
                <Link href="/auth/giris?next=/uye-ol" className="text-brand-600 hover:underline">
                  giriş yapmanız
                </Link>{" "}
                gerekiyor.
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
