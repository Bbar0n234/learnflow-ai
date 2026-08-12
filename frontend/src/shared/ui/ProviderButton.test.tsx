import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { FormEvent } from "react";
import { describe, expect, it, vi } from "vitest";

import { ProviderButton, type AuthProvider } from "./ProviderButton";

// Integration (компонент целиком под RTL, без сети и провайдеров): кнопка входа
// через внешнего провайдера. Проверяем её публичный контракт — какое имя кнопка
// объявляет ассистивным технологиям, что делает с кликом, что делает `disabled`
// и что она безопасна внутри формы.
//
// Брендовые цвета знаков (Google — четыре фирменных, GitHub — #24292f/#f0f0f0 по
// теме, Яндекс — красная «Я» на белом круге) здесь не проверяются: jsdom не
// исполняет CSS и не резолвит `dark:`-варианты, а ассерт на атрибут `fill`
// зеркалил бы разметку вместо цвета. Живая сверка обеих тем уже сделана треком
// (summary T6.4, замеры `getComputedStyle`), регресс — ручной кейс {T6.5}.

// Таблица провайдеров — `Record<AuthProvider, string>`: состав союза сторожит
// `tsc`, а не рантайм-ассерт. Появится в союзе четвёртый провайдер (VK ID снят
// решением архитектора по 149-ФЗ, design-brief блок 8) — `make check-fe`
// покраснеет на недостающем ключе, исчезнет один — на лишнем.
const PROVIDER_LABELS: Record<AuthProvider, string> = {
  yandex: "Войти с Яндекс ID",
  google: "Войти через Google",
  github: "Войти через GitHub",
};

const PROVIDERS = Object.entries(PROVIDER_LABELS) as [AuthProvider, string][];

describe("ProviderButton", () => {
  it.each(PROVIDERS)(
    "объявляет провайдера %s фирменной подписью",
    (provider, label) => {
      render(<ProviderButton provider={provider} />);

      expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
    },
  );

  // Знак — DOM-факт, который jsdom исполняет: он обязан быть в разметке (иначе
  // кнопка провайдера неотличима от обычной) и обязан быть скрыт от скринридера
  // (подпись рядом уже называет провайдера, дублировать его графикой нечем).
  it.each(PROVIDERS)(
    "рисует знак %s и прячет его от скринридера",
    (provider) => {
      const { container } = render(<ProviderButton provider={provider} />);

      const mark = container.querySelector("svg");
      expect(mark).toBeInTheDocument();
      expect(mark).toHaveAttribute("aria-hidden", "true");
    },
  );

  it("берёт переданный label вместо фирменной подписи", () => {
    render(<ProviderButton provider="google" label="Продолжить с Google" />);

    expect(
      screen.getByRole("button", { name: "Продолжить с Google" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Войти через Google" }),
    ).not.toBeInTheDocument();
  });

  // Класс здесь — сам наблюдаемый контракт: `className` существует затем, чтобы
  // потребитель посадил кнопку в свою геометрию, не форкая компонент; иначе
  // проброс не наблюдаем вовсе (jsdom раскладку не считает).
  it("пробрасывает className в корень кнопки", () => {
    render(<ProviderButton provider="yandex" className="mt-6" />);

    expect(
      screen.getByRole("button", { name: "Войти с Яндекс ID" }),
    ).toHaveClass("mt-6");
  });

  it("зовёт onClick по клику ровно один раз", async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    render(<ProviderButton provider="yandex" onClick={onClick} />);

    await user.click(screen.getByRole("button", { name: "Войти с Яндекс ID" }));

    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("не отвечает на клик, когда disabled", async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    render(<ProviderButton provider="github" onClick={onClick} disabled />);

    const button = screen.getByRole("button", { name: "Войти через GitHub" });
    expect(button).toBeDisabled();

    await user.click(button);

    expect(onClick).not.toHaveBeenCalled();
  });

  // Кнопка живёт внутри `<form>` auth-экрана: дефолтный `type="submit"` отправлял
  // бы форму логина вместо перехода к провайдеру. Проверяем поведением, а не
  // ассертом на атрибут.
  it("не отправляет форму, в которой стоит", async () => {
    const onSubmit = vi.fn((event: FormEvent) => event.preventDefault());
    const user = userEvent.setup();
    render(
      <form onSubmit={onSubmit}>
        <ProviderButton provider="google" />
      </form>,
    );

    await user.click(
      screen.getByRole("button", { name: "Войти через Google" }),
    );

    expect(onSubmit).not.toHaveBeenCalled();
  });
});
