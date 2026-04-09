"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { post, ApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

function getPasswordStrength(pw: string): { score: number; label: string; color: string } {
  let score = 0;
  if (pw.length >= 8) score++;
  if (/[A-Z]/.test(pw)) score++;
  if (/\d/.test(pw)) score++;
  if (/[!@#$%^&*(),.?":{}|<>_\-\+\=\[\]\\\/]/.test(pw)) score++;
  const labels = ["", "Zayıf", "Orta", "İyi", "Güçlü"];
  const colors = ["", "bg-red-500", "bg-orange-400", "bg-yellow-400", "bg-green-500"];
  return { score, label: labels[score] ?? "", color: colors[score] ?? "" };
}

function PasswordRules({ password }: { password: string }) {
  const rules = [
    { label: "En az 8 karakter", met: password.length >= 8 },
    { label: "En az 1 büyük harf", met: /[A-Z]/.test(password) },
    { label: "En az 1 rakam", met: /\d/.test(password) },
    { label: "En az 1 özel karakter (!@#$%^&* vb.)", met: /[!@#$%^&*(),.?":{}|<>_\-\+\=\[\]\\\/]/.test(password) },
  ];
  return (
    <ul className="mt-1.5 space-y-0.5">
      {rules.map((r) => (
        <li
          key={r.label}
          className={`flex items-center gap-1.5 text-xs ${r.met ? "text-green-600" : "text-gray-400"}`}
        >
          <span>{r.met ? "✓" : "○"}</span>
          {r.label}
        </li>
      ))}
    </ul>
  );
}

export default function KayitPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<{ email?: string; password?: string; confirm?: string }>({});
  const [loading, setLoading] = useState(false);

  const strength = getPasswordStrength(password);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    const errs: typeof fieldErrors = {};
    if (!email.includes("@")) errs.email = "Geçerli bir e-posta girin";
    if (strength.score < 4) errs.password = "Şifre tüm kuralları karşılamalıdır";
    if (password !== confirmPassword) errs.confirm = "Şifreler eşleşmiyor";
    if (Object.keys(errs).length > 0) {
      setFieldErrors(errs);
      return;
    }
    setFieldErrors({});

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
              onChange={(e) => { setEmail(e.target.value); setFieldErrors((f) => ({ ...f, email: undefined })); }}
              placeholder="ornek@email.com"
              required
              className={`w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 ${fieldErrors.email ? "border-red-400" : "border-gray-300"}`}
            />
            {fieldErrors.email && (
              <p className="text-xs text-red-600 mt-1">{fieldErrors.email}</p>
            )}
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Şifre
            </label>
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => { setPassword(e.target.value); setFieldErrors((f) => ({ ...f, password: undefined })); }}
                placeholder="••••••••"
                required
                className={`w-full border rounded-lg px-3 py-2 pr-16 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 ${fieldErrors.password ? "border-red-400" : "border-gray-300"}`}
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                tabIndex={-1}
                aria-label={showPassword ? "Şifreyi gizle" : "Şifreyi göster"}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 hover:text-gray-600 select-none"
              >
                {showPassword ? "Gizle" : "Göster"}
              </button>
            </div>
            {password.length > 0 && (
              <div className="mt-1.5">
                <div className="flex gap-1 h-1.5">
                  {[1, 2, 3, 4].map((i) => (
                    <div
                      key={i}
                      className={`flex-1 rounded-full transition-all ${i <= strength.score ? strength.color : "bg-gray-200"}`}
                    />
                  ))}
                </div>
                {strength.label && (
                  <p className="text-xs text-gray-500 mt-0.5">{strength.label}</p>
                )}
              </div>
            )}
            <PasswordRules password={password} />
            {fieldErrors.password && (
              <p className="text-xs text-red-600 mt-1">{fieldErrors.password}</p>
            )}
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Şifre Tekrar
            </label>
            <div className="relative">
              <input
                type={showConfirm ? "text" : "password"}
                value={confirmPassword}
                onChange={(e) => { setConfirmPassword(e.target.value); setFieldErrors((f) => ({ ...f, confirm: undefined })); }}
                placeholder="••••••••"
                required
                className={`w-full border rounded-lg px-3 py-2 pr-16 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 ${fieldErrors.confirm ? "border-red-400" : "border-gray-300"}`}
              />
              <button
                type="button"
                onClick={() => setShowConfirm((v) => !v)}
                tabIndex={-1}
                aria-label={showConfirm ? "Şifreyi gizle" : "Şifreyi göster"}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 hover:text-gray-600 select-none"
              >
                {showConfirm ? "Gizle" : "Göster"}
              </button>
            </div>
            {fieldErrors.confirm && (
              <p className="text-xs text-red-600 mt-1">{fieldErrors.confirm}</p>
            )}
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
