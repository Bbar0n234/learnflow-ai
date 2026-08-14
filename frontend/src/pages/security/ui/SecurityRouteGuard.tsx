import { ReactNode } from "react";
import { Navigate } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { queryKeys } from "@/shared/api/query-keys";
import { getIsAdminFromAccessToken, getMe } from "@/shared/api/auth";
import { getAccessToken } from "@/shared/api/client";
import { LoadingState } from "@/shared/ui/StateScreen";

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
    queryKey: queryKeys.auth.me,
    queryFn: () => getMe() as Promise<UserWithAdmin>,
    enabled: !!token,
    staleTime: Infinity,
  });

  if (isLoading) {
    return <LoadingState className="h-full" />;
  }

  // Check JWT for is_admin claim as fallback.
  const isAdmin = user?.is_admin === true || getIsAdminFromAccessToken(token);

  if (!isAdmin) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}
