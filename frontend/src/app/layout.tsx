import type { Metadata } from "next";
import "./globals.css";
import Link from "next/link";
import { AuthProvider } from "@/context/AuthContext";

export const metadata: Metadata = {
  title: "STOTTO — Spor Toto Karar Destek",
  description: "Spor Toto 15 maç analiz ve kupon optimizasyon sistemi",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="tr">
      <body className="min-h-screen bg-gray-50">
        <AuthProvider>
          <nav className="bg-brand-900 text-white shadow-md">
            <div className="max-w-7xl mx-auto px-4 py-3 flex items-center gap-6">
              <Link href="/" className="text-xl font-bold tracking-tight hover:opacity-80">
                STOTTO
              </Link>
              <Link href="/kupon" className="text-sm hover:opacity-80">
                Kupon Optimizasyonu
              </Link>
            </div>
          </nav>
          <main className="max-w-7xl mx-auto px-4 py-6">{children}</main>
        </AuthProvider>
      </body>
    </html>
  );
}
