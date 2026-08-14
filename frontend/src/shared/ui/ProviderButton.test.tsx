import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { FormEvent } from "react";
import { describe, expect, it, vi } from "vitest";

import { NBSP, PROVIDER_LABELS } from "@/test/provider-labels";

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

// Эталонные подписи — общие с суитой экрана (`@/test/provider-labels`), одной
// копией на весь набор: подписи задаёт этот компонент, а ищут по ним кнопку обе
// суиты, и две копии разъезжаются с продом порознь. Там же — сторож состава
// союза `AuthProvider` через `Record<AuthProvider, string>` и объяснение, почему
// копия своя, а не импорт `DEFAULT_LABELS` из компонента.
const PROVIDERS = Object.entries(PROVIDER_LABELS) as [AuthProvider, string][];

describe("ProviderButton", () => {
  it.each(PROVIDERS)(
    "объявляет провайдера %s фирменной подписью",
    (provider, label) => {
      render(<ProviderButton provider={provider} />);

      expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
    },
  );

  // Сторож неразрывного пробела. U+00A0 между «Яндекс» и «ID» стоит в мокапе
  // намеренно: ниже `lg` карточка тянется во всю ширину, и с обычным пробелом
  // «ID» уезжает на вторую строку в отрыве от названия. Сам перенос в jsdom не
  // наблюдаем (раскладки нет), зато наблюдаем его носитель — символ в подписи,
  // и кейс смотрит именно на **отрендеренную** подпись, а не на константу
  // набора: пробел сравнивается посимвольно, без нормализации.
  //
  // Первая половина — что нужный символ на месте; вторая — что кнопка не
  // находится по тому же имени с обычным пробелом. Вторая нужна потому, что до
  // этого кейса набор сравнивал подпись как раз с обычным пробелом и был
  // зелёным при неправильном проде.
  it("держит «Яндекс ID» неразрывным пробелом, чтобы подпись не переносилась", () => {
    render(<ProviderButton provider="yandex" />);

    const button = screen.getByRole("button", {
      name: PROVIDER_LABELS.yandex,
    });
    expect(button.textContent).toContain(`Яндекс${NBSP}ID`);

    const withPlainSpace = PROVIDER_LABELS.yandex.replace(NBSP, " ");
    expect(
      screen.queryByRole("button", { name: withPlainSpace }),
    ).not.toBeInTheDocument();
  });

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
      screen.queryByRole("button", { name: PROVIDER_LABELS.google }),
    ).not.toBeInTheDocument();
  });

  // Класс здесь — сам наблюдаемый контракт: `className` существует затем, чтобы
  // потребитель посадил кнопку в свою геометрию, не форкая компонент; иначе
  // проброс не наблюдаем вовсе (jsdom раскладку не считает).
  it("пробрасывает className в корень кнопки", () => {
    render(<ProviderButton provider="yandex" className="mt-6" />);

    expect(
      screen.getByRole("button", { name: PROVIDER_LABELS.yandex }),
    ).toHaveClass("mt-6");
  });

  it("зовёт onClick по клику ровно один раз", async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    render(<ProviderButton provider="yandex" onClick={onClick} />);

    await user.click(
      screen.getByRole("button", { name: PROVIDER_LABELS.yandex }),
    );

    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("не отвечает на клик, когда disabled", async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    render(<ProviderButton provider="github" onClick={onClick} disabled />);

    const button = screen.getByRole("button", { name: PROVIDER_LABELS.github });
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
      screen.getByRole("button", { name: PROVIDER_LABELS.google }),
    );

    expect(onSubmit).not.toHaveBeenCalled();
  });
});
