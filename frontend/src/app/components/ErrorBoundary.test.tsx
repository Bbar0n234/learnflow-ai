import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { logger } from "@/shared/lib/logger";

import { ErrorBoundary } from "./ErrorBoundary";

// Unit (feat-013, блок 2 брифа): последний экран продукта — то, что видит
// пользователь, когда рендер упал. Правка была визуальной: своя вёрстка с
// sans-заголовком и сырым `<button>` уступила брендовому шаблону состояния.
// Логирование при этом трогать было нельзя — бриф требует сохранить
// `componentDidCatch → logger.error`, иначе унификация вида молча стоила бы
// диагностики. Обе половины проверяются здесь: что видит человек и что
// уезжает в лог. Геометрию нового шаблона (serif-заголовок, ширина сцены,
// вариант кнопки) jsdom не видит — её сторожит ручной кейс {T4.7}; из
// переезда на общий шаблон здесь наблюдаема сцена и её доступное имя.
//
// `logger` — граница наблюдаемости (внешний эффект), поэтому именно факт и
// форма вызова и есть контракт: тот случай, когда spy уместен (testing.md §
// Дубли). React дополнительно печатает пойманную ошибку в `console.error` —
// его глушим, чтобы вывод прогона не тонул в шуме.

function Boom(): never {
  throw new Error("Разорвало рендер");
}

afterEach(() => {
  vi.restoreAllMocks();
});

function renderBoundary() {
  vi.spyOn(console, "error").mockImplementation(() => {});
  const logged = vi.spyOn(logger, "error").mockImplementation(() => {});

  render(
    <ErrorBoundary>
      <Boom />
    </ErrorBoundary>,
  );

  return { logged };
}

describe("ErrorBoundary", () => {
  it("shows the branded failure screen instead of the broken subtree", () => {
    renderBoundary();

    expect(
      screen.getByRole("heading", { name: "Что-то пошло не так" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Произошла непредвиденная ошибка. Попробуйте обновить страницу.",
      ),
    ).toBeInTheDocument();
    // Экран даёт действие, а не только сообщение.
    expect(
      screen.getByRole("button", { name: "Обновить страницу" }),
    ).toBeInTheDocument();
    // И это именно общий брендовый экран, а не своя вёрстка с похожими
    // строками: сцена та же и названа так же, как на панелях сферы и
    // артефакта («Иллюстрация: ошибка»). Заголовок, подпись и подпись кнопки
    // сами по себе экран не различают — дотрековая вёрстка несла те же самые.
    expect(
      screen.getByRole("img", { name: "Иллюстрация: ошибка" }),
    ).toBeInTheDocument();
  });

  it("still reports the caught error to the logger", () => {
    const { logged } = renderBoundary();

    expect(logged).toHaveBeenCalledWith(
      "render error",
      expect.objectContaining({ message: "Разорвало рендер" }),
      expect.anything(),
    );
  });

  it("renders the children untouched while nothing throws", () => {
    render(
      <ErrorBoundary>
        <p>Рабочий экран</p>
      </ErrorBoundary>,
    );

    expect(screen.getByText("Рабочий экран")).toBeInTheDocument();
  });
});
