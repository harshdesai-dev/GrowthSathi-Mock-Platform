import { GoogleOAuthProvider } from "@react-oauth/google";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import { useState } from "react";

import { AppErrorBoundary } from "../components/common/AppErrorBoundary";
import { AuthProvider } from "../auth/AuthContext";

export function AppProviders({ children }: PropsWithChildren) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            refetchOnWindowFocus: false,
            retry: 1,
            staleTime: 30_000,
          },
        },
      }),
  );
  const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;
  const content = <AuthProvider>{children}</AuthProvider>;

  return (
    <AppErrorBoundary>
      <QueryClientProvider client={queryClient}>
        {googleClientId ? (
          <GoogleOAuthProvider clientId={googleClientId}>
            {content}
          </GoogleOAuthProvider>
        ) : (
          content
        )}
      </QueryClientProvider>
    </AppErrorBoundary>
  );
}
