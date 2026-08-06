import { AxiosError, AxiosHeaders } from "axios";
import { describe, expect, it } from "vitest";

import { getApiErrorMessage, getProblemMessageFromBody } from "./api-error";

// Unit: RFC 9457 problem+json message extraction. Pure functions — no network.

function axiosErrorWithResponse(status: number, data: unknown): AxiosError {
  const err = new AxiosError("Request failed");
  err.response = {
    status,
    statusText: "",
    data,
    headers: {},
    config: { headers: new AxiosHeaders() },
  };
  return err;
}

describe("getProblemMessageFromBody", () => {
  it("prefers the body detail field", () => {
    expect(getProblemMessageFromBody(422, { detail: "Поле обязательно" })).toBe(
      "Поле обязательно",
    );
  });

  it("falls back to title when detail is absent", () => {
    expect(getProblemMessageFromBody(409, { title: "Конфликт ресурса" })).toBe(
      "Конфликт ресурса",
    );
  });

  it("prefers detail over title when both present", () => {
    expect(
      getProblemMessageFromBody(422, { detail: "Деталь", title: "Заголовок" }),
    ).toBe("Деталь");
  });

  it.each([
    [401, "Недостаточно прав / требуется вход"],
    [403, "Недостаточно прав / требуется вход"],
    [404, "Не найдено"],
    [409, "Конфликт: ресурс уже существует"],
    [422, "Некорректные данные"],
    [500, "Ошибка сервера, попробуйте позже"],
    [503, "Ошибка сервера, попробуйте позже"],
    [418, "Произошла ошибка, попробуйте позже"],
  ])(
    "maps status %i to its category when body has no message",
    (status, expected) => {
      expect(getProblemMessageFromBody(status, null)).toBe(expected);
    },
  );

  it("ignores empty-string detail and falls back to category", () => {
    expect(getProblemMessageFromBody(404, { detail: "" })).toBe("Не найдено");
  });
});

describe("getApiErrorMessage", () => {
  it("extracts the problem detail from an AxiosError response", () => {
    const err = axiosErrorWithResponse(422, { detail: "Невалидный URL" });
    expect(getApiErrorMessage(err)).toBe("Невалидный URL");
  });

  it("reports a timeout when the request was aborted with no response", () => {
    const err = new AxiosError("timeout", "ECONNABORTED");
    expect(getApiErrorMessage(err)).toBe("Превышено время ожидания");
  });

  it("reports server unreachable for a network error with no response", () => {
    const err = new AxiosError("Network Error");
    expect(getApiErrorMessage(err)).toBe("Сервер недоступен, попробуйте позже");
  });

  it("returns a generic message for non-Axios errors", () => {
    expect(getApiErrorMessage(new Error("boom"))).toBe(
      "Произошла ошибка, попробуйте позже",
    );
    expect(getApiErrorMessage(null)).toBe("Произошла ошибка, попробуйте позже");
  });
});
