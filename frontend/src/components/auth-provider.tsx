"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import {
  accessToken,
  api,
  clearSession,
  refreshToken,
  storeSession,
} from "@/lib/api";
import type { Me, TokenResponse } from "@/lib/types";

interface AuthState {
  me: Me | null;
  loading: boolean;
  workspaceId: string | null;
  switchWorkspace: (workspaceId: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState>({
  me: null,
  loading: true,
  workspaceId: null,
  switchWorkspace: async () => undefined,
  logout: async () => undefined,
});

const PUBLIC = new Set(["/", "/login", "/register", "/architecture"]);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);

  const loadMe = useCallback(async () => {
    if (!accessToken()) {
      setMe(null);
      setLoading(false);
      return;
    }
    try {
      const next = await api<Me>("/api/v1/auth/me");
      setMe(next);
      const current =
        window.localStorage.getItem("opspilot-workspace-id") ?? next.workspaces[0]?.id ?? null;
      if (current) window.localStorage.setItem("opspilot-workspace-id", current);
      setWorkspaceId(current);
    } catch {
      clearSession();
      setMe(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadMe();
  }, [loadMe, pathname]);

  useEffect(() => {
    if (PUBLIC.has(pathname)) return;
    if (!loading && !accessToken()) {
      router.replace("/login");
    }
  }, [loading, pathname, router]);

  async function switchWorkspace(nextId: string) {
    const tokens = await api<TokenResponse>("/api/v1/auth/workspace", {
      method: "POST",
      body: JSON.stringify({ workspace_id: nextId }),
    });
    storeSession(tokens.access_token, tokens.refresh_token, tokens.workspace_id);
    setWorkspaceId(tokens.workspace_id);
    await loadMe();
  }

  async function logout() {
    const token = refreshToken();
    if (token) {
      try {
        await api("/api/v1/auth/logout", {
          method: "POST",
          body: JSON.stringify({ refresh_token: token }),
        });
      } catch {
        /* local logout still proceeds */
      }
    }
    clearSession();
    setMe(null);
    setWorkspaceId(null);
    router.replace("/login");
  }

  if (!PUBLIC.has(pathname) && loading) {
    return <div className="min-h-screen animate-pulse bg-surface" />;
  }

  return (
    <AuthContext.Provider value={{ me, loading, workspaceId, switchWorkspace, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
