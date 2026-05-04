import { ReactNode } from "react";
import { Navigate } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { getMe } from "@/shared/api/auth";
import { getAccessToken } from "@/shared/api/client";

interface UserWithAdmin {
  id: string;
  name: string;
  is_admin?: boolean;
}

/**
 * RBAC guard for /security route.
 * Checks if current user has is_admin claim in JWT or user profile.
 */
export function SecurityRouteGuard({ children }: { children: ReactNode }) {
  const token = getAccessToken();
  const { data: user, isLoading } = useQuery({
    queryKey: ["auth", "me"],
    queryFn: () => getMe() as Promise<UserWithAdmin>,
    enabled: !!token,
    staleTime: Infinity,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-muted-foreground">Загрузка...</p>
      </div>
    );
  }

  // Check JWT for is_admin claim as fallback
  let isAdmin = false;
  if (user?.is_admin) {
    isAdmin = true;
  } else if (token) {
    try {
      const parts = token.split(".");
      if (parts.length === 3) {
        const payloadEncoded = parts[1];
        if (payloadEncoded) {
          const payload = JSON.parse(atob(payloadEncoded));
          isAdmin = payload.is_admin === true;
        }
      }
    } catch {
      // Ignore JWT parse errors
    }
  }

  if (!isAdmin) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}
