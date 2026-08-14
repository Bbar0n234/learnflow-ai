import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AuthLayout } from "./AuthLayout";

// Integration (компонент целиком под RTL): брендовая рамка auth-страницы.
// Проверяем ровно её контракт как обёртки — слот `children` доходит до DOM
// нетронутым, тэглайн имеет дефолт и перекрывается, сцена `auth-hero` рисуется
// со своей подписью.
//
// Геометрия (колонки 1fr/440px, паддинги 56px и 40/48px, ритм 22px, wordmark
// 38px, сцена 460px) и поведение ниже брейкпоинта `lg` здесь не проверяются:
// jsdom не считает раскладку и не применяет media-варианты Tailwind. Живая
// сверка по числам уже сделана треком (summary T6.4), регресс — ручные кейсы
// {T6.6}, {T6.7}.

describe("AuthLayout", () => {
  it("отдаёт слот children потребителю как есть", () => {
    render(
      <AuthLayout>
        <form aria-label="Карточка формы">
          <button type="submit">Войти</button>
        </form>
      </AuthLayout>,
    );

    const card = screen.getByRole("form", { name: "Карточка формы" });
    expect(card).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Войти" })).toBeInTheDocument();
  });

  it("подписывается дефолтным тэглайном, когда свой не передан", () => {
    render(<AuthLayout>{null}</AuthLayout>);

    expect(
      screen.getByText(
        "Учитесь со своим ИИ-наставником: проекты, чаты и сфера знаний, которая растёт вместе с вами.",
      ),
    ).toBeInTheDocument();
  });

  it("берёт переданный тэглайн вместо дефолта", () => {
    render(<AuthLayout tagline="Свой тэглайн">{null}</AuthLayout>);

    expect(screen.getByText("Свой тэглайн")).toBeInTheDocument();
    expect(screen.queryByText(/Учитесь со своим ИИ-наставником/)).toBeNull();
  });

  it("рисует сцену auth-hero с подписью для скринридера", () => {
    render(<AuthLayout>{null}</AuthLayout>);

    const scene = screen.getByRole("img", {
      name: "Иллюстрация: Электрик приветствует",
    });
    expect(scene).toHaveAttribute("src", expect.stringMatching(/auth-hero/));
  });

  // Класс здесь — сам наблюдаемый контракт: `className` существует ровно затем,
  // чтобы потребитель (`pages/login` из feat-008) посадил экран в свою
  // геометрию, не форкая компонент. jsdom раскладку не считает.
  it("пробрасывает className в корень", () => {
    const { container } = render(
      <AuthLayout className="mt-6">{null}</AuthLayout>,
    );

    expect(container.firstElementChild).toHaveClass("mt-6");
  });
});
