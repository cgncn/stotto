"use client";

import { useState } from "react";
import { post } from "@/lib/api";

export default function AdminPage() {
  const [token, setToken] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [weekCode, setWeekCode] = useState("");
  const [fixtureIds, setFixtureIds] = useState("");
  const [poolId, setPoolId] = useState("");

  async function login() {
    try {
      const res = await post<{ access_token: string }>("/auth/login", { email, password });
      setToken(res.access_token);
      setMessage("Giriş başarılı.");
    } catch (e: any) {
      setMessage(`Hata: ${e.message}`);
    }
  }

  function authHeaders() {
    return { Authorization: `Bearer ${token}` };
  }

  async function triggerImport() {
    const ids = fixtureIds.split(",").map((s) => parseInt(s.trim(), 10)).filter(Boolean);
    try {
      const res = await post<{ detail: string; task_id: string }>(
        "/admin/weekly-import",
        { week_code: weekCode, fixture_external_ids: ids }
      );
      setMessage(`İçe aktarma başlatıldı — task: ${res.task_id}`);
    } catch (e: any) {
      setMessage(`Hata: ${e.message}`);
    }
  }

  async function recompute() {
    try {
      const res = await post<{ detail: string; task_id: string }>(
        `/admin/recompute-week/${poolId}`,
        {}
      );
      setMessage(`Yeniden hesaplama başlatıldı — task: ${res.task_id}`);
    } catch (e: any) {
      setMessage(`Hata: ${e.message}`);
    }
  }

  if (!token) {
    return (
      <div className="max-w-sm mx-auto mt-20 bg-white rounded-xl shadow p-8">
        <h1 className="text-xl font-bold mb-4 text-gray-800">Yönetici Girişi</h1>
        <input
          type="email"
          placeholder="E-posta"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full border rounded px-3 py-2 mb-3 text-sm"
        />
        <input
          type="password"
          placeholder="Şifre"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full border rounded px-3 py-2 mb-4 text-sm"
        />
        <button
          onClick={login}
          className="w-full bg-brand-600 text-white py-2 rounded hover:bg-brand-700 text-sm"
        >
          Giriş Yap
        </button>
        {message && <p className="mt-3 text-sm text-red-500">{message}</p>}
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-800">Yönetim Paneli</h1>
        <button
          onClick={() => setToken("")}
          className="text-sm text-gray-400 hover:text-red-500"
        >
          Çıkış
        </button>
      </div>

      {message && (
        <div className="mb-4 bg-blue-50 border border-blue-200 rounded p-3 text-sm text-blue-800">
          {message}
        </div>
      )}

      {/* Weekly import */}
      <div className="bg-white rounded-xl shadow p-5 mb-4">
        <h2 className="font-semibold text-gray-700 mb-3">Haftalık İçe Aktarma</h2>
        <input
          type="text"
          placeholder="Hafta kodu (örn. 2025-W15)"
          value={weekCode}
          onChange={(e) => setWeekCode(e.target.value)}
          className="w-full border rounded px-3 py-2 mb-2 text-sm"
        />
        <textarea
          placeholder="Fixture ID'leri virgülle ayırın (15 adet)"
          value={fixtureIds}
          onChange={(e) => setFixtureIds(e.target.value)}
          rows={3}
          className="w-full border rounded px-3 py-2 mb-3 text-sm"
        />
        <button
          onClick={triggerImport}
          className="bg-brand-600 text-white text-sm px-4 py-2 rounded hover:bg-brand-700"
        >
          İçe Aktar
        </button>
      </div>

      {/* Recompute */}
      <div className="bg-white rounded-xl shadow p-5">
        <h2 className="font-semibold text-gray-700 mb-3">Yeniden Hesaplama</h2>
        <div className="flex gap-2">
          <input
            type="number"
            placeholder="Havuz ID"
            value={poolId}
            onChange={(e) => setPoolId(e.target.value)}
            className="border rounded px-3 py-2 text-sm w-32"
          />
          <button
            onClick={recompute}
            className="bg-amber-500 text-white text-sm px-4 py-2 rounded hover:bg-amber-600"
          >
            Yeniden Hesapla
          </button>
        </div>
      </div>
    </div>
  );
}
