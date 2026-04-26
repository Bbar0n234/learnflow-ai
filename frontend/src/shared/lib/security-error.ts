import { AxiosError } from "axios";

export const SECURITY_VIOLATION_MESSAGE =
  "Запрос отклонён системой безопасности. Отредактируйте содержимое и попробуйте ещё раз.";

export function isSecurityViolation(error: unknown): boolean {
  if (!(error instanceof AxiosError)) return false;
  if (error.response?.status !== 422) return false;
  const detail = error.response.data?.detail;
  return (
    typeof detail === "object" &&
    detail !== null &&
    (detail as { error?: unknown }).error === "security_policy_violation"
  );
}
