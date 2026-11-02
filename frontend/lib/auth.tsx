"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, post } from "./api";

export type Me = {
  id: number;
  full_name: string;
  username: string;
  role: { code: string; name: string };
  must_change_password: boolean;
  permissions: string[];
};

type Ctx = { me: Me | null; loading: boolean; can: (p: string) => boolean; reload: () => Promise<void>; logout: () => Promise<void> };

const AuthCtx = createContext<Ctx>({ me: null, loading: true, can: () => false, reload: async () => {}, logout: async () => {} });

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    try {
      setMe(await api<Me>("/api/auth/me"));
    } catch {
      setMe(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  // Keep the session alive while the person is active; it ends after 30 idle minutes on the server.
  useEffect(() => {
    if (!me) return;
    let last = Date.now();
    const bump = () => (last = Date.now());
    window.addEventListener("keydown", bump);
    window.addEventListener("mousedown", bump);
    const t = setInterval(() => {
      if (Date.now() - last < 10 * 60 * 1000) post("/api/auth/refresh").catch(() => {});
    }, 10 * 60 * 1000);
    return () => {
      clearInterval(t);
      window.removeEventListener("keydown", bump);
      window.removeEventListener("mousedown", bump);
    };
  }, [me]);

  const logout = useCallback(async () => {
    await post("/api/auth/logout").catch(() => {});
    setMe(null);
    window.location.href = "/login";
  }, []);

  const can = useCallback((p: string) => !!me?.permissions.includes(p), [me]);
  return <AuthCtx.Provider value={{ me, loading, can, reload, logout }}>{children}</AuthCtx.Provider>;
}

export const useAuth = () => useContext(AuthCtx);
