"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { post, ApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

export default function KayitPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const body: Record<string, string> = { email, password };
      if (displayName.trim()) body.display_name = displayName.trim();
      const res = await post<{ access_token: string }>("/auth/register", body);
      login(res.access_token);
      router.push("/");
    } catch (err) {
      if (err instanceof ApiError) {
        try {
          const detail = JSON.parse(err.message);
          if (detail?.detail) {
            setError(String(detail.detail));
          } else {
            setError("Kayıt başarısız. Lütfen tekrar deneyin.");
          }
        } catch {
          setError(err.message || "Kayıt başarısız. Lütfen tekrar deneyin.");
        }
      } else {
        setError("Kayıt başarısız. Lütfen tekrar deneyin.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-[70vh] flex items-center justify-center">
      <div className="w-full max-w-sm bg-white rounded-xl shadow-md p-8">
        <h1 className="text-2xl font-bold text-gray-800 mb-6">Kayıt Ol</h1>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Ad Soyad <span className="text-gray-400 font-normal">(isteğe bağlı)</span>
            </label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="Adınız Soyadınız"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              E-posta
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="ornek@email.com"
              required
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Şifre <span className="text-gray-400 font-normal">(en az 8 karakter)</span>
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
              minLength={8}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>
          {error && (
            <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-brand-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? "Kayıt yapılıyor…" : "Kayıt Ol"}
          </button>
        </form>
        <p className="mt-5 text-center text-sm text-gray-500">
          Zaten hesabınız var mı?{" "}
          <Link href="/auth/giris" className="text-brand-600 hover:underline font-medium">
            Giriş yapın →
          </Link>
        </p>
      </div>
    </div>
  );
}
