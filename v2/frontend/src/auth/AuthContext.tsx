import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, ApiError, AUTH_EXPIRED_EVENT } from "../api/client";
import type { User } from "../api/types";

type Status = "loading" | "authed" | "anon";
interface Ctx {
  status: Status; user: User | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  can: (permission: string) => boolean;
}
const AuthCtx = createContext<Ctx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>("loading");
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    api<User>("/auth/me").then((u) => { setUser(u); setStatus("authed"); }).catch(() => setStatus("anon"));
    const expired = () => { setUser(null); setStatus("anon"); };
    window.addEventListener(AUTH_EXPIRED_EVENT, expired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, expired);
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const u = await api<User>("/auth/login", { method: "POST", body: { username, password } });
    setUser(u); setStatus("authed");
  }, []);
  const logout = useCallback(async () => {
    try { await api("/auth/logout", { method: "POST" }); } catch (e) { if (!(e instanceof ApiError)) throw e; }
    setUser(null); setStatus("anon");
  }, []);
  const can = useCallback((p: string) => !!user?.permissions.includes(p), [user]);

  const value = useMemo(() => ({ status, user, login, logout, can }), [status, user, login, logout, can]);
  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export function useAuth(): Ctx {
  const c = useContext(AuthCtx);
  if (!c) throw new Error("useAuth outside AuthProvider");
  return c;
}
