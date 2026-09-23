"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { UserOut } from "@/lib/types";
import { getMe, login as apiLogin, register as apiRegister } from "@/lib/api";
import { clearStoredToken, setStoredToken } from "@/lib/auth-storage";

type AuthStatus = "loading" | "authenticated" | "unauthenticated";

interface AuthContextValue {
  status: AuthStatus;
  user: UserOut | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<UserOut | null>(null);
  const queryClient = useQueryClient();

  useEffect(() => {
    // DEMO ONLY: this environment has no database, so the real
    // register/login/getMe round trip can never succeed. Skip straight to an
    // authenticated demo user so the app shell is reachable.
    //
    // To restore real auth, replace this effect body with:
    //
    //   const token = getStoredToken();
    //   if (!token) { setStatus("unauthenticated"); return; }
    //   getMe()
    //     .then((me) => { setUser(me); setStatus("authenticated"); })
    //     .catch(() => { clearStoredToken(); setStatus("unauthenticated"); });
    setUser({ id: "demo-user", email: "demo@agentforge.local", created_at: new Date().toISOString() });
    setStatus("authenticated");
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const token = await apiLogin(email, password);
      setStoredToken(token.access_token);
      const me = await getMe();
      queryClient.clear();
      setUser(me);
      setStatus("authenticated");
    },
    [queryClient],
  );

  const register = useCallback(
    async (email: string, password: string) => {
      await apiRegister(email, password);
      await login(email, password);
    },
    [login],
  );

  const logout = useCallback(() => {
    clearStoredToken();
    queryClient.clear();
    setUser(null);
    setStatus("unauthenticated");
  }, [queryClient]);

  return (
    <AuthContext.Provider value={{ status, user, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }

  return context;
}
