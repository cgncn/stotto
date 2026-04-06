"use client";

import {
  createContext,
  useContext,
  useState,
  useEffect,
  ReactNode,
} from "react";
import { authedGet } from "@/lib/api";

const TOKEN_KEY = "stotto_token";

interface UserProfile {
  id: number;
  email: string;
  role: "FREE" | "SUBSCRIBER" | "ADMIN";
  display_name: string | null;
  subscription_status: string | null;
  subscription_expires_at: string | null;
}

interface AuthState {
  token: string | null;
  user: UserProfile | null;
  isSubscriber: boolean;
  login: (token: string) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthState>({
  token: null,
  user: null,
  isSubscriber: false,
  login: () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<UserProfile | null>(null);

  const fetchProfile = async (t: string) => {
    try {
      const data = await authedGet<UserProfile>("/users/me", t);
      setUser(data);
    } catch {
      // Token invalid — clear it
      localStorage.removeItem(TOKEN_KEY);
      setToken(null);
      setUser(null);
    }
  };

  useEffect(() => {
    const stored = localStorage.getItem(TOKEN_KEY);
    if (stored) {
      setToken(stored);
      fetchProfile(stored);
    }
  }, []);

  const login = (t: string) => {
    localStorage.setItem(TOKEN_KEY, t);
    setToken(t);
    fetchProfile(t);
  };

  const logout = () => {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
  };

  const isSubscriber =
    user?.role === "SUBSCRIBER" || user?.role === "ADMIN";

  return (
    <AuthContext.Provider value={{ token, user, isSubscriber, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}

export function useSubscription() {
  const { isSubscriber } = useContext(AuthContext);
  return { isSubscriber };
}
