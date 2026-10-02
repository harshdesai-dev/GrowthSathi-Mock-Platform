import {
  type PropsWithChildren,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  endSession,
  exchangeGoogleCredential,
  fetchCurrentUser,
  fetchStudentProfile,
  patchStudentProfile,
  refreshSession,
  type AuthUser,
  type ProfileInput,
} from "../api/client";
import { ApiError } from "../api/errors";
import {
  AuthContext,
  type AuthContextValue,
  type AuthStatus,
} from "./auth-context";

export function AuthProvider({ children }: PropsWithChildren) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<AuthUser | null>(null);
  const accessToken = useRef<string | null>(null);
  const restored = useRef(false);
  const refreshInFlight = useRef<Promise<string> | null>(null);

  const clearSession = useCallback(() => {
    accessToken.current = null;
    setUser(null);
    setStatus("unauthenticated");
  }, []);

  const refreshAccess = useCallback(async () => {
    if (!refreshInFlight.current) {
      refreshInFlight.current = refreshSession()
        .then((session) => {
          accessToken.current = session.access_token;
          return session.access_token;
        })
        .finally(() => {
          refreshInFlight.current = null;
        });
    }
    return refreshInFlight.current;
  }, []);

  useEffect(() => {
    if (restored.current) return;
    restored.current = true;
    void refreshAccess()
      .then(fetchCurrentUser)
      .then((currentUser) => {
        setUser(currentUser);
        setStatus("authenticated");
      })
      .catch(() => clearSession());
  }, [clearSession, refreshAccess]);

  const loginWithGoogle = useCallback(async (credential: string) => {
    const session = await exchangeGoogleCredential(credential);
    accessToken.current = session.access_token;
    setUser(session.user);
    setStatus("authenticated");
    return session.user;
  }, []);

  const withAccess = useCallback(
    async <T,>(operation: (token: string) => Promise<T>): Promise<T> => {
      let token = accessToken.current;
      if (!token) token = await refreshAccess();
      try {
        return await operation(token);
      } catch (error) {
        if (!(error instanceof ApiError) || error.status !== 401) throw error;
        token = await refreshAccess();
        return operation(token);
      }
    },
    [refreshAccess],
  );

  const getProfile = useCallback(
    () => withAccess((token) => fetchStudentProfile(token)),
    [withAccess],
  );

  const saveProfile = useCallback(
    async (profile: ProfileInput) => {
      const updated = await withAccess((token) =>
        patchStudentProfile(token, profile),
      );
      const currentUser = await withAccess((token) => fetchCurrentUser(token));
      setUser(currentUser);
      return updated;
    },
    [withAccess],
  );

  const logout = useCallback(async () => {
    await endSession();
    clearSession();
  }, [clearSession]);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      loginWithGoogle,
      logout,
      getProfile,
      saveProfile,
      withAccess,
    }),
    [
      status,
      user,
      loginWithGoogle,
      logout,
      getProfile,
      saveProfile,
      withAccess,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
