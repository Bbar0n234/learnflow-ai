import { AxiosError } from "axios";

export const SECURITY_VIOLATION_MESSAGE =
  "Запрос отклонён системой безопасности. Отредактируйте содержимое и попробуйте ещё раз.";

export function isSecurityViolation(error: unknown): boolean {
  if (!(error instanceof AxiosError)) return false;
  if (error.response?.status !== 422) return false;
  // RFC 9457 problem+json: машинный код ошибки в поле type
  const type = error.response.data?.type;
  return type === "urn:learnflow:security-policy-violation";
}
