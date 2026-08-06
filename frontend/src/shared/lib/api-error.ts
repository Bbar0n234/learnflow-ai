import { AxiosError } from "axios";

/**
 * Тип-guard для тела problem+json: { detail?, title? }.
 * Без поля `any` — узкая проверка по образцу security-error.ts.
 */
interface ProblemBody {
  detail?: string;
  title?: string;
}

function isProblemBody(value: unknown): value is ProblemBody {
  return (
    value !== null &&
    typeof value === "object" &&
    (Object.prototype.hasOwnProperty.call(value, "detail") ||
      Object.prototype.hasOwnProperty.call(value, "title"))
  );
}

function categoryByStatus(status: number): string {
  if (status === 401 || status === 403)
    return "Недостаточно прав / требуется вход";
  if (status === 404) return "Не найдено";
  if (status === 409) return "Конфликт: ресурс уже существует";
  if (status === 422) return "Некорректные данные";
  if (status >= 500) return "Ошибка сервера, попробуйте позже";
  return "Произошла ошибка, попробуйте позже";
}

/**
 * Извлекает осмысленное сообщение из тела problem+json.
 * Приоритет: detail → title → категория по статусу.
 * Используется в fetch-ветке SSE (где нет AxiosError).
 */
export function getProblemMessageFromBody(
  status: number,
  body: unknown,
): string {
  if (isProblemBody(body)) {
    if (typeof body.detail === "string" && body.detail) return body.detail;
    if (typeof body.title === "string" && body.title) return body.title;
  }
  return categoryByStatus(status);
}

/**
 * Единый парсер RFC 9457 problem+json для AxiosError и прочих ошибок.
 *
 * Никогда не возвращает сырые `error.message` / «HTTP 500» —
 * только осмысленный русский текст.
 *
 * FSD: shared/lib без barrel; импорт по файлу @/shared/lib/api-error.
 */
export function getApiErrorMessage(error: unknown): string {
  if (error instanceof AxiosError) {
    if (!error.response) {
      // Нет ответа сервера: таймаут или сеть
      if (error.code === "ECONNABORTED") return "Превышено время ожидания";
      return "Сервер недоступен, попробуйте позже";
    }
    return getProblemMessageFromBody(
      error.response.status,
      error.response.data,
    );
  }
  // Не-AxiosError (DOMException, строка, null, undefined и др.)
  return "Произошла ошибка, попробуйте позже";
}
