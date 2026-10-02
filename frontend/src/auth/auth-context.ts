import { createContext, useContext } from "react";

import type { AuthUser, ProfileInput, StudentProfile } from "../api/client";

export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

export interface AuthContextValue {
  status: AuthStatus;
  user: AuthUser | null;
  loginWithGoogle: (credential: string) => Promise<AuthUser>;
  logout: () => Promise<void>;
  getProfile: () => Promise<StudentProfile>;
  saveProfile: (profile: ProfileInput) => Promise<StudentProfile>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider.");
  return context;
}
