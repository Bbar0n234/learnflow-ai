import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";

import { ErrorCard, LoadingState, StateScreen } from "./StateScreen";

// Integration (компонент целиком, без сети): публичный контракт трёх примитивов
// «не-контента» — он же контракт волны 2 (T2, T4, T6). Проверяем, какие слоты
// появляются и исчезают, что делают дефолты и обработчик «Повторить».
//
// Цвета, геометрия и анимация спиннера здесь не проверяются: jsdom не исполняет
// CSS — вид форм против мокапа уехал в ручные кейсы {T1.5}–{T1.8}.

describe("StateScreen", () => {
  it("рисует подпись как единственный обязательный слот", () => {
    render(<StateScreen description="Выберите артефакт из списка" />);

    expect(screen.getByText("Выберите артефакт из списка")).toBeInTheDocument();
    expect(screen.queryByRole("heading")).not.toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("показывает заголовок вторым уровнем, когда он передан", () => {
    render(
      <StateScreen
        title="Страница не найдена"
        description="Такой страницы у нас нет"
      />,
    );

    expect(
      screen.getByRole("heading", { level: 2, name: "Страница не найдена" }),
    ).toBeInTheDocument();
  });

  it("рисует сцену с переданной подписью, когда задан scene", () => {
    render(
      <StateScreen
        scene="not-found"
        alt="Электрик разводит руками у оборванного провода"
        description="Такой страницы у нас нет"
      />,
    );

    const illustration = screen.getByRole("img", {
      name: "Электрик разводит руками у оборванного провода",
    });
    expect(illustration).toHaveAttribute("src", expect.stringMatching(/\S/));
  });

  it("отдаёт слот действия потребителю как есть", () => {
    render(
      <StateScreen
        description="Такой страницы у нас нет"
        action={<a href="/">На главную</a>}
      />,
    );

    expect(screen.getByRole("link", { name: "На главную" })).toHaveAttribute(
      "href",
      "/",
    );
  });

  // Класс здесь — сам наблюдаемый контракт: `illustrationClassName` существует
  // ровно затем, чтобы потребитель задал сцене утверждённую ширину
  // (`max-w-[360px]` для 404 и т.д.), а `StateScreen` её не хардкодил.
  it("прокидывает illustrationClassName на сцену", () => {
    render(
      <StateScreen
        scene="not-found"
        alt="Электрик разводит руками у оборванного провода"
        description="Такой страницы у нас нет"
        illustrationClassName="max-w-[360px] w-full"
      />,
    );

    expect(
      screen.getByRole("img", {
        name: "Электрик разводит руками у оборванного провода",
      }),
    ).toHaveClass("max-w-[360px]");
  });

  // Плановая правка plan-review №2: базовый `flex-1` не прибит намертво —
  // потребитель перекрывает его своим классом, а не форкает компонент.
  // Класс — наблюдаемый контракт: другого способа увидеть перекрытие в jsdom нет.
  it("даёт классу потребителя перекрыть базовый flex-1", () => {
    const { container } = render(
      <StateScreen
        description="Такой страницы у нас нет"
        className="flex-none"
      />,
    );

    const root = container.firstElementChild;
    expect(root).toHaveClass("flex-none");
    expect(root).not.toHaveClass("flex-1");
  });
});

describe("LoadingState", () => {
  it("подписывается «Загрузка…» без явного label", () => {
    render(<LoadingState />);

    expect(screen.getByText("Загрузка…")).toBeInTheDocument();
  });

  // Спиннер — DOM-факт, а не CSS: сама иконка обязана быть в разметке и быть
  // скрытой от скринридера (подпись «Загрузка…» уже озвучивает состояние, и
  // дублировать его безымянной графикой нечем). Вращение — ручной кейс {T1.8}.
  it("рисует спиннер и прячет его от скринридера", () => {
    const { container } = render(<LoadingState />);

    const spinner = container.querySelector("svg");
    expect(spinner).toBeInTheDocument();
    expect(spinner).toHaveAttribute("aria-hidden", "true");
  });

  it("берёт переданный label вместо дефолта", () => {
    render(<LoadingState label="Загружаю сферу…" />);

    expect(screen.getByText("Загружаю сферу…")).toBeInTheDocument();
    expect(screen.queryByText("Загрузка…")).not.toBeInTheDocument();
  });
});

describe("ErrorCard", () => {
  it("показывает сообщение об ошибке", () => {
    render(<ErrorCard message="Не удалось загрузить чаты" />);

    expect(screen.getByText("Не удалось загрузить чаты")).toBeInTheDocument();
  });

  it("не рисует «Повторить» без onRetry", () => {
    render(<ErrorCard message="Не удалось загрузить чаты" />);

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("зовёт onRetry по клику на «Повторить»", async () => {
    const onRetry = vi.fn();
    const user = userEvent.setup();
    render(<ErrorCard message="Не удалось загрузить чаты" onRetry={onRetry} />);

    const retry = screen.getByRole("button", { name: "Повторить" });
    // `type="button"` — часть контракта, а не мелочь: у потребителя волны 2
    // карточка ошибки может стоять внутри формы, и кнопка по умолчанию её
    // отправит вместо перезапуска квери.
    expect(retry).toHaveAttribute("type", "button");

    await user.click(retry);

    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("берёт retryLabel вместо дефолтного «Повторить»", () => {
    render(
      <ErrorCard
        message="Не удалось загрузить чаты"
        onRetry={vi.fn()}
        retryLabel="Попробовать снова"
      />,
    );

    expect(
      screen.getByRole("button", { name: "Попробовать снова" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Повторить" }),
    ).not.toBeInTheDocument();
  });
});

describe("примитивы состояний", () => {
  // Волна 2 сажает эти формы в чужую геометрию (панель, узкий сайдбар) через
  // root-`className`; если проброс потеряется, отладка уедет в вёрстку
  // потребителя. Класс — наблюдаемый контракт, jsdom не считает раскладку.
  const roots: [string, (className: string) => ReactElement][] = [
    ["StateScreen", (c) => <StateScreen description="текст" className={c} />],
    ["LoadingState", (c) => <LoadingState className={c} />],
    ["ErrorCard", (c) => <ErrorCard message="текст" className={c} />],
  ];

  it.each(roots)("%s пробрасывает className в корень", (_name, renderNode) => {
    const { container } = render(renderNode("mt-6"));

    expect(container.firstElementChild).toHaveClass("mt-6");
  });
});
