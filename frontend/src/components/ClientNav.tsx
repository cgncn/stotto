"use client";

import Link from "next/link";
import { useAuth } from "@/context/AuthContext";

export function ClientNav() {
  const { user, logout } = useAuth();

  if (!user) {
    return (
      <div className="flex gap-4 text-sm">
        <Link href="/auth/giris" className="text-gray-300 hover:text-white">
          Giriş
        </Link>
        <Link href="/auth/kayit" className="text-gray-300 hover:text-white">
          Kayıt
        </Link>
      </div>
    );
  }

  return (
    <div className="flex gap-4 text-sm items-center">
      {user.role === "ADMIN" && (
        <Link
          href="/admin"
          className="bg-yellow-500 hover:bg-yellow-400 text-black font-semibold px-3 py-1 rounded text-xs"
        >
          ⚙ Admin
        </Link>
      )}
      <Link href="/uye-ol" className="text-gray-300 hover:text-white">
        Üye Ol
      </Link>
      <Link href="/hesap" className="text-gray-300 hover:text-white">
        {user.display_name ?? user.email}
      </Link>
    </div>
  );
}
