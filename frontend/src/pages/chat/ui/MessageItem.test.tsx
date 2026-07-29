import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import type { Message, MessagePart } from "@/shared/api/chats";
import { renderWithProviders } from "@/test/test-utils";

import { MessageItem } from "./MessageItem";

// Смоук-набор фазы T2.3 (реализатор): лента истории рендерится, разворот
// показывает вызов и результат, усечение маркировано, ход из одного текста
// ленты не получает. Это проверка механизма, а не покрытия — полноценный
// поведенческий набор пишет test-author и волен заменить этот файл целиком.

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

describe("smoke: лента в истории", () => {
  it("рендерит строку действия с подписью из реестра", () => {
    renderMessage(
      message([
        {
          type: "tool_call",
          call_id: "c-1",
          tool: "firecrawl_search",
          args: '{"query": "изоляция контекста"}',
          args_truncated: false,
          status: "success",
          result_preview: "нашлось",
          result_truncated: false,
        },
      ]),
    );

    expect(
      screen.getByRole("button", { name: /Ищу в интернете/ }),
    ).toBeInTheDocument();
    expect(screen.getByText(/«изоляция контекста»/)).toBeInTheDocument();
  });

  it("разворот показывает сырое имя, args и результат", async () => {
    renderMessage(
      message([
        {
          type: "tool_call",
          call_id: "c-1",
          tool: "firecrawl_search",
          args: '{"query": "изоляция контекста"}',
          args_truncated: false,
          status: "success",
          result_preview: "нашлось восемь источников",
          result_truncated: false,
        },
      ]),
    );

    await userEvent.click(screen.getByRole("button", { name: /Ищу/ }));

    expect(screen.getByText("firecrawl_search")).toBeInTheDocument();
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
          tool: "firecrawl_search",
          args: '{"query": "x"}',
          args_truncated: false,
          status: "success",
          result_preview: LONG,
          result_truncated: true,
        },
      ]),
    );

    await userEvent.click(screen.getByRole("button", { name: /Ищу/ }));

    expect(screen.getByText("обрезано сервером")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Показать всё, что пришло/ }),
    ).toBeInTheDocument();
  });

  it("усечение аргументов не метит зону результата", async () => {
    renderMessage(
      message([
        {
          type: "tool_call",
          call_id: "c-1",
          tool: "firecrawl_search",
          args: '{"query": "очень длинный запр',
          args_truncated: true,
          status: "success",
          result_preview: "нашлось",
          result_truncated: false,
        },
      ]),
    );

    await userEvent.click(screen.getByRole("button", { name: /Ищу/ }));

    expect(screen.getAllByText("обрезано сервером")).toHaveLength(1);
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

  it("несколько вызовов — одна лента строк", () => {
    renderMessage(
      message([
        { type: "reasoning", content: "думаю" },
        {
          type: "tool_call",
          call_id: "c-1",
          tool: "firecrawl_search",
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

    expect(screen.getByRole("button", { name: /Рассуждения/ })).toBeVisible();
    expect(
      screen.getByRole("button", { name: /Ищу в интернете/ }),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: /Обновляю память проекта/ }),
    ).toBeVisible();
    expect(screen.getByText("ошибка")).toBeInTheDocument();
    expect(screen.getByText("Готово.")).toBeInTheDocument();
  });
});
