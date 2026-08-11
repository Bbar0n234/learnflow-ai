import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import type { Message, MessagePart } from "@/shared/api/chats";
import { renderWithProviders } from "@/test/test-utils";

import { MessageItem } from "./MessageItem";

// Integration: сохранённый ход агента на экране. Сообщение ассистента —
// последовательность typed parts, и `MessageItem` обязан показать по ней тот же
// след действий, который пользователь видел живым: подпись из реестра вместо
// машинного имени, разворот с зонами «Вызов» / «Результат», честный маркер
// усечения и статус вызова текстом, а не одним цветом.
//
// Файл начинался смоук-набором фазы T2.3; test-author оставил кейсы, которые
// проверяют контракт, и дополнил их поведением, которого не было: три статуса
// вызова, обрезанные аргументы на экране, незнакомый инструмент, редакция.

function message(parts: MessagePart[], content = "готово"): Message {
  return {
    id: "m1",
    role: "assistant",
    content,
    created_at: null,
    artifacts: [],
    parts,
  };
}

function renderMessage(msg: Message) {
  return renderWithProviders(
    <MemoryRouter>
      <MessageItem message={msg} projectId="p1" chatId="c1" />
    </MemoryRouter>,
  );
}

const LONG = "результат ".repeat(40);

function toolCallPart(
  overrides: Partial<Extract<MessagePart, { type: "tool_call" }>> = {},
): MessagePart {
  return {
    type: "tool_call",
    call_id: "c-1",
    tool: "search_web",
    args: '{"query": "langgraph"}',
    args_truncated: false,
    status: "success",
    result_preview: "нашлось",
    result_truncated: false,
    ...overrides,
  };
}

describe("лента в истории", () => {
  it("рендерит строку действия с подписью из реестра", () => {
    renderMessage(
      message([
        {
          type: "tool_call",
          call_id: "c-1",
          tool: "search_web",
          args: '{"query": "изоляция контекста"}',
          args_truncated: false,
          status: "success",
          result_preview: "нашлось",
          result_truncated: false,
        },
      ]),
    );

    expect(
      screen.getByRole("button", { name: /Искал в интернете/ }),
    ).toBeInTheDocument();
    expect(screen.getByText(/«изоляция контекста»/)).toBeInTheDocument();
  });

  it("разворот показывает сырое имя, args и результат", async () => {
    renderMessage(
      message([
        {
          type: "tool_call",
          call_id: "c-1",
          tool: "search_web",
          args: '{"query": "изоляция контекста"}',
          args_truncated: false,
          status: "success",
          result_preview: "нашлось восемь источников",
          result_truncated: false,
        },
      ]),
    );

    await userEvent.click(screen.getByRole("button", { name: /Искал/ }));

    expect(screen.getByText("search_web")).toBeInTheDocument();
    expect(screen.getByText(/query: изоляция контекста/)).toBeInTheDocument();
    expect(screen.getByText("нашлось восемь источников")).toBeInTheDocument();
    expect(screen.getByText("Вызов")).toBeInTheDocument();
    expect(screen.getByText("Результат")).toBeInTheDocument();
  });

  it("маркирует усечение и не обещает большего", async () => {
    renderMessage(
      message([
        {
          type: "tool_call",
          call_id: "c-1",
          tool: "search_web",
          args: '{"query": "x"}',
          args_truncated: false,
          status: "success",
          result_preview: LONG,
          result_truncated: true,
        },
      ]),
    );

    await userEvent.click(screen.getByRole("button", { name: /Искал/ }));

    // Бейджа усечения нет (решение архитектора на приёмке) — честность несёт
    // формулировка кнопки: она не обещает недостающего.
    expect(
      screen.getByRole("button", { name: "Показать всё, что пришло" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Показать полностью" }),
    ).not.toBeInTheDocument();
  });

  it("усечение аргументов не метит зону результата", async () => {
    renderMessage(
      message([
        {
          type: "tool_call",
          call_id: "c-1",
          tool: "search_web",
          args: '{"query": "очень длинный запр',
          args_truncated: true,
          status: "success",
          result_preview: "нашлось",
          result_truncated: false,
        },
      ]),
    );

    await userEvent.click(screen.getByRole("button", { name: /Искал/ }));

    expect(
      screen.getByText("Аргументы оборваны сервером — не разобраны."),
    ).toBeInTheDocument();
    expect(screen.getByText("нашлось")).toBeInTheDocument();
  });

  it("незавершённый вызов виден статусом, а не ошибкой", () => {
    renderMessage(
      message([
        {
          type: "tool_call",
          call_id: "c-1",
          tool: "run_subagent",
          args: '{"agent_type": "judge"}',
          args_truncated: false,
          status: "pending",
          result_preview: "",
          result_truncated: false,
        },
      ]),
    );

    expect(screen.getByText("не завершён")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Проверяющий субагент/ }),
    ).toBeInTheDocument();
  });

  it("ход из одного текста ленты не получает", () => {
    renderMessage(message([{ type: "text", content: "Просто ответ." }]));

    expect(screen.getByText("Просто ответ.")).toBeInTheDocument();
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("пустые parts дают degraded-рендер по content", () => {
    renderMessage(message([], "плоский контент"));

    expect(screen.getByText("плоский контент")).toBeInTheDocument();
  });

  // Смоук фазы T2.6: в истории субагент живёт одной строкой — заданием и
  // вердиктом в развороте, без вложенной хронологии (её событий чекпоинтер не
  // хранит, streaming.md § История: typed parts).
  it("субагент в истории разворачивается в задание и ответ без вложенных шагов", async () => {
    renderMessage(
      message([
        {
          type: "tool_call",
          call_id: "c-sub",
          tool: "run_subagent",
          args: JSON.stringify({
            agent_type: "judge",
            task: "Проверь черновик выводов по изоляции контекста.",
          }),
          args_truncated: false,
          status: "success",
          result_preview: "Три замечания по формулировкам.",
          result_truncated: false,
        },
      ]),
    );

    const row = screen.getByRole("button", {
      name: /Проверяющий субагент/,
    });
    await userEvent.click(row);

    expect(screen.getByText("run_subagent")).toBeInTheDocument();
    expect(
      screen.getByText("Проверь черновик выводов по изоляции контекста."),
    ).toBeInTheDocument();
    expect(screen.getByText("Ответ субагента")).toBeInTheDocument();
    expect(
      screen.getByText("Три замечания по формулировкам."),
    ).toBeInTheDocument();
    // Вложенных строк в истории нет — единственная кнопка-строка тут своя.
    expect(screen.getAllByRole("button", { expanded: true })).toHaveLength(1);
  });

  it("несколько вызовов — одна лента строк", () => {
    renderMessage(
      message([
        { type: "reasoning", content: "думаю" },
        {
          type: "tool_call",
          call_id: "c-1",
          tool: "search_web",
          args: '{"query": "a"}',
          args_truncated: false,
          status: "success",
          result_preview: "ok",
          result_truncated: false,
        },
        {
          type: "tool_call",
          call_id: "c-2",
          tool: "update_section",
          args: '{"section_id": "Субагенты"}',
          args_truncated: false,
          status: "error",
          result_preview: "не вышло",
          result_truncated: false,
        },
        { type: "text", content: "Готово." },
      ]),
    );

    expect(screen.getByRole("button", { name: /Рассуждал/ })).toBeVisible();
    expect(
      screen.getByRole("button", { name: /Искал в интернете/ }),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: /Обновлял память проекта/ }),
    ).toBeVisible();
    expect(screen.getByText("ошибка")).toBeInTheDocument();
    expect(screen.getByText("Готово.")).toBeInTheDocument();
  });
});

describe("статусы вызова в истории", () => {
  it.each([
    { status: "success" as const, visible: "успешно" },
    { status: "error" as const, visible: "ошибка" },
    { status: "pending" as const, visible: "не завершён" },
  ])(
    "вызов со статусом $status читается словом «$visible»",
    ({ status, visible }) => {
      renderMessage(
        message([
          toolCallPart({
            status,
            result_preview: status === "pending" ? "" : "результат",
          }),
        ]),
      );

      // Статус выражен текстом, а не одним цветом: цветовая шкала недоступна
      // скринридеру и не различима при дальтонизме.
      expect(screen.getByText(visible)).toBeInTheDocument();
    },
  );

  it("незавершённый вызов объясняет отсутствие результата в развороте", async () => {
    renderMessage(
      message([toolCallPart({ status: "pending", result_preview: "" })]),
    );

    await userEvent.click(screen.getByRole("button", { name: /Искал/ }));

    expect(
      screen.getByText("Вызов не завершён — результата нет."),
    ).toBeInTheDocument();
  });
});

describe("большие и обрезанные данные", () => {
  const CUT_ARGS = '{"query": "очень длинный запр';

  it("обрезанные аргументы на экран сырой строкой не идут", async () => {
    renderMessage(
      message([toolCallPart({ args: CUT_ARGS, args_truncated: true })]),
    );

    await userEvent.click(screen.getByRole("button", { name: /Искал/ }));

    // Оборванный посреди JSON текст читать нечем — вместо него сказано, что
    // аргументы обрезаны. Заодно подпись строки остаётся без дополнения.
    expect(screen.queryByText(/очень длинный запр/)).not.toBeInTheDocument();
    expect(
      screen.getByText("Аргументы оборваны сервером — не разобраны."),
    ).toBeInTheDocument();
    expect(screen.getByText("search_web")).toBeInTheDocument();
  });

  it("аргументы нештатной формы показываются сырыми — обрезки в них нет", async () => {
    renderMessage(
      message([toolCallPart({ args: "не json вовсе", args_truncated: false })]),
    );

    await userEvent.click(screen.getByRole("button", { name: /Искал/ }));

    expect(screen.getByText("не json вовсе")).toBeInTheDocument();
    expect(screen.queryByText("обрезано сервером")).not.toBeInTheDocument();
  });

  it("короткий результат показан целиком, без обещания раскрытия", async () => {
    renderMessage(message([toolCallPart({ result_preview: "нашлось" })]));

    await userEvent.click(screen.getByRole("button", { name: /Искал/ }));

    expect(screen.getByText("нашлось")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Показать/ }),
    ).not.toBeInTheDocument();
  });

  it("длинный неусечённый результат раскрывается полностью и сворачивается", async () => {
    renderMessage(
      message([
        toolCallPart({ result_preview: LONG, result_truncated: false }),
      ]),
    );

    await userEvent.click(screen.getByRole("button", { name: /Искал/ }));

    // Обрезки нет — кнопка обещает ровно то, что покажет.
    const expand = screen.getByRole("button", { name: "Показать полностью" });

    await userEvent.click(expand);
    expect(
      screen.getByRole("button", { name: "Свернуть" }),
    ).toBeInTheDocument();
  });

  it("оба флага усечения независимы: обрезанный результат не метит вызов", async () => {
    renderMessage(
      message([toolCallPart({ result_preview: LONG, result_truncated: true })]),
    );

    await userEvent.click(screen.getByRole("button", { name: /Искал/ }));

    // Усечение результата видно по кнопке его зоны; аргументы целы и разобраны.
    expect(
      screen.getByRole("button", { name: "Показать всё, что пришло" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/query: langgraph/)).toBeInTheDocument();
  });
});

describe("инструмент вне реестра подписей", () => {
  it("показан сырым именем с нейтральной пометкой источника", () => {
    renderMessage(
      message([toolCallPart({ tool: "acme_do_thing", call_id: "c-9" })]),
    );

    // Пользовательский MCP-инструмент подписи не имеет и иметь не обязан —
    // строка ленты всё равно читается в той же грамматике.
    expect(
      screen.getByRole("button", { name: /acme_do_thing/ }),
    ).toBeInTheDocument();
    expect(screen.getByText(/инструмент MCP/)).toBeInTheDocument();
  });
});

describe("рассуждения и совместимость", () => {
  it("рассуждение свёрнуто в строку и раскрывается своим текстом", async () => {
    renderMessage(
      message([
        { type: "reasoning", content: "Сначала проверю память проекта." },
        { type: "text", content: "Готово." },
      ]),
    );

    // В истории ход завершён: рассуждение подписано следом, а не процессом.
    expect(
      screen.queryByText("Сначала проверю память проекта."),
    ).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /Рассуждал/ }));

    expect(
      screen.getByText("Сначала проверю память проекта."),
    ).toBeInTheDocument();
  });

  it("сообщение без поля parts рендерится плоским content", () => {
    const legacy: Message = {
      id: "m-old",
      role: "assistant",
      content: "Ответ из старого кэша",
      created_at: null,
      artifacts: [],
    };

    renderMessage(legacy);

    expect(screen.getByText("Ответ из старого кэша")).toBeInTheDocument();
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("заблокированный ход показывает одну заглушку и ни одной строки действий", () => {
    renderMessage({
      ...message([
        toolCallPart(),
        { type: "text", content: "секретный ответ" },
      ]),
      redacted: true,
    });

    // Редакция вытесняет ход целиком: ни рассуждений, ни строк вызовов
    // заблокированного хода на экране не остаётся.
    expect(
      screen.getByText("[Сообщение скрыто в целях безопасности]"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Искал в интернете/)).not.toBeInTheDocument();
    expect(screen.queryByText("секретный ответ")).not.toBeInTheDocument();
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });
});
