import { act, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import type { ReactElement } from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import type { Message, MessagePart } from "@/shared/api/chats";
import type { SSEEvent } from "@/shared/api/sse";
import {
  applyStreamEvent,
  type AgentFeedItem,
  type AgentFeedState,
} from "@/shared/lib/agent-feed";
import { useStreamStore } from "@/stores/stream-store";
import { renderWithProviders } from "@/test/test-utils";

import { MessageItem } from "./MessageItem";
import { MessageList } from "./MessageList";
import type { StreamEndReason } from "./StreamEndNotice";

// Integration: the streaming region of the message feed. Live activity is the
// same feed the history renders (`shared/lib/agent-feed`), and on top of it the
// image generation placeholder lives for exactly as long as a `generate_image`
// call stays unclosed — it appears with the call's args and goes away on the
// call's result (feat-001, T2.4: покрытие переехало с `tool_start`/`tool_end`).

// jsdom has no layout — MessageList auto-scrolls a ref into view on mount.
beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

/** Лента, собранная тем же редьюсером, что работает в сторе на live-потоке. */
function feedFrom(events: SSEEvent[]): AgentFeedItem[] {
  const initial: AgentFeedState = { feed: [], redacted: false };
  return events.reduce(
    (state, event) => applyStreamEvent(state, event),
    initial,
  ).feed;
}

interface RenderOptions {
  isStreaming?: boolean;
  endNotice?: StreamEndReason | null;
}

function listTree(feed: AgentFeedItem[], options: RenderOptions = {}) {
  const ui: ReactElement = (
    <MemoryRouter>
      <MessageList
        messages={[]}
        isStreaming={options.isStreaming ?? true}
        feed={feed}
        streamingArtifacts={[]}
        projectId="p1"
        chatId="c1"
        streamError={null}
        endNotice={options.endNotice ?? null}
      />
    </MemoryRouter>
  );
  return ui;
}

function renderFeed(feed: AgentFeedItem[], options: RenderOptions = {}) {
  return renderWithProviders(listTree(feed, options));
}

const GENERATION_LABEL = "Идёт генерация изображения";

function imageCall(callId: string, prompt: string): SSEEvent[] {
  return [
    { type: "tool_call_started", call_id: callId, tool: "generate_image" },
    {
      type: "tool_call_args",
      call_id: callId,
      args: JSON.stringify({ prompt }),
      truncated: false,
    },
  ];
}

describe("MessageList — image generation placeholder", () => {
  it("renders one placeholder card per unfinished generate_image call", () => {
    renderFeed(
      feedFrom([
        ...imageCall("call-1", "кот на подоконнике"),
        ...imageCall("call-2", "график производной"),
      ]),
    );

    expect(
      screen.getAllByRole("status", { name: GENERATION_LABEL }),
    ).toHaveLength(2);
  });

  it("drops the placeholder once the call returns its result", () => {
    renderFeed(
      feedFrom([
        ...imageCall("call-1", "кот на подоконнике"),
        {
          type: "tool_result",
          call_id: "call-1",
          tool: "generate_image",
          status: "success",
          content: "готово",
          truncated: false,
        },
      ]),
    );

    expect(
      screen.queryByRole("status", { name: GENERATION_LABEL }),
    ).not.toBeInTheDocument();
  });

  it("shows no placeholder for a non-image tool call", () => {
    renderFeed(
      feedFrom([
        {
          type: "tool_call_started",
          call_id: "call-9",
          tool: "firecrawl_search",
        },
        {
          type: "tool_call_args",
          call_id: "call-9",
          args: JSON.stringify({ query: "langgraph" }),
          truncated: false,
        },
      ]),
    );

    // Работа инструмента видна строкой ленты, а не карточкой генерации.
    expect(screen.getByText(/Ищу в интернете/)).toBeInTheDocument();
    expect(
      screen.queryByRole("status", { name: GENERATION_LABEL }),
    ).not.toBeInTheDocument();
  });

  it("shows no placeholder cards on an empty feed", () => {
    renderFeed([]);

    expect(
      screen.queryByRole("status", { name: GENERATION_LABEL }),
    ).not.toBeInTheDocument();
  });
});

// Смоук фазы T2.5: живость и терминальные состояния. Покрытие снятого
// индикатора «агент думает» переехало сюда — на строку-паузу, которая приняла
// его роль.
describe("MessageList — живость ленты", () => {
  it("держит строку-паузу, пока в ленте нет ни одного события", () => {
    renderFeed([]);

    expect(
      screen.getByRole("status", { name: "Агент думает" }),
    ).toBeInTheDocument();
  });

  it("снимает строку-паузу с первым содержательным событием", () => {
    renderFeed(
      feedFrom([
        { type: "tool_call_started", call_id: "call-1", tool: "get_section" },
      ]),
    );

    expect(
      screen.queryByRole("status", { name: "Агент думает" }),
    ).not.toBeInTheDocument();
  });

  // Регрессия финального интеграционного прогона: на живом ходе экран замер на
  // 10,65 с (с +135,95 с до +146,60 с) — все строки ленты к этому моменту
  // завершились, идущей строки не было, а пауза показывалась только пока лента
  // пуста. На проводе в это время шли `heartbeat` с шагом 5 с: молчал не
  // сервер, а интерфейс. Признак показа — «в ленте нет идущей строки», и он
  // обязан закрывать любой промежуток хода, а не только окно до первого события.
  it("возвращает строку-паузу в промежутке между завершённым и следующим действием", () => {
    renderFeed(
      feedFrom([
        {
          type: "tool_call_started",
          call_id: "call-1",
          tool: "firecrawl_search",
        },
        {
          type: "tool_result",
          call_id: "call-1",
          tool: "firecrawl_search",
          status: "success",
          content: "нашлось",
          truncated: false,
        },
      ]),
    );

    expect(
      screen.getByRole("status", { name: "Агент думает" }),
    ).toBeInTheDocument();
  });

  it("возвращает паузу, когда отработал и субагент, и его вложенные шаги", () => {
    const started: SSEEvent[] = [
      { type: "tool_call_started", call_id: "sub-1", tool: "run_subagent" },
      {
        type: "tool_call_started",
        call_id: "step-1",
        tool: "firecrawl_scrape",
        parent_call_id: "sub-1",
      },
    ];
    // Пока субагент работает, на экране есть идущие строки — паузе места нет.
    const { rerender } = renderFeed(feedFrom(started));
    expect(
      screen.queryByRole("status", { name: "Агент думает" }),
    ).not.toBeInTheDocument();

    rerender(
      listTree(
        feedFrom([
          ...started,
          {
            type: "tool_result",
            call_id: "step-1",
            tool: "firecrawl_scrape",
            status: "success",
            content: "страница",
            truncated: false,
            parent_call_id: "sub-1",
          },
          {
            type: "tool_result",
            call_id: "sub-1",
            tool: "run_subagent",
            status: "success",
            content: "вердикт",
            truncated: false,
          },
        ]),
      ),
    );

    expect(
      screen.getByRole("status", { name: "Агент думает" }),
    ).toBeInTheDocument();
  });

  it("не подменяет паузой растущий текст ответа", () => {
    renderFeed(
      feedFrom([
        {
          type: "tool_call_started",
          call_id: "call-1",
          tool: "firecrawl_search",
        },
        {
          type: "tool_result",
          call_id: "call-1",
          tool: "firecrawl_search",
          status: "success",
          content: "нашлось",
          truncated: false,
        },
        { type: "text_chunk", content: "Вот что нашлось" },
      ]),
    );

    // Хвостовой текст поток дописывает прямо сейчас — это и есть живая строка,
    // паузе рядом с ней места нет.
    expect(
      screen.queryByRole("status", { name: "Агент думает" }),
    ).not.toBeInTheDocument();
  });

  it("подписывает хвостовое рассуждение процессом и держит его развёрнутым", () => {
    renderFeed(
      feedFrom([{ type: "reasoning_chunk", content: "надо поискать" }]),
    );

    expect(screen.getByText("Рассуждает")).toBeInTheDocument();
    expect(screen.queryByText("Рассуждения")).not.toBeInTheDocument();
    // Пока поток дописывает рассуждение, оно видно без клика — иначе живой
    // ход снова становится немым.
    expect(screen.getByText("надо поискать")).toBeInTheDocument();
  });

  it("меняет строку-паузу на индикатор проверки ответа", () => {
    useStreamStore.getState().setReviewing(true);

    renderFeed([]);

    expect(screen.getByText("Проверяем ответ...")).toBeInTheDocument();
    expect(
      screen.queryByRole("status", { name: "Агент думает" }),
    ).not.toBeInTheDocument();
  });

  it("сворачивает рассуждение, когда поток ушёл в следующее действие", () => {
    renderFeed(
      feedFrom([
        { type: "reasoning_chunk", content: "надо поискать" },
        {
          type: "tool_call_started",
          call_id: "call-1",
          tool: "firecrawl_search",
        },
      ]),
    );

    expect(screen.getByText("Рассуждения")).toBeInTheDocument();
    expect(screen.queryByText("Рассуждает")).not.toBeInTheDocument();
  });

  it("показывает счётчик времени только у действия, идущего дольше порога", async () => {
    vi.useFakeTimers();
    try {
      const feed = feedFrom([
        {
          type: "tool_call_started",
          call_id: "call-1",
          tool: "firecrawl_search",
        },
      ]);
      renderFeed(feed);

      // Порог проверяется с обеих сторон: короткому действию цифры не нужны —
      // счётчик нужен там, где иначе начинается тишина. Запрос идёт по форме
      // счётчика (`m:ss`), а не по конкретному значению: ассерт на «0:04» до
      // сдвига часов истинен при любом пороге и не сторожит ничего.
      await act(async () => {
        vi.advanceTimersByTime(2000);
      });
      expect(screen.queryByText(/^\d+:\d{2}$/)).not.toBeInTheDocument();

      await act(async () => {
        vi.advanceTimersByTime(2000);
      });

      expect(screen.getByText("0:04")).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});

// Смоук фазы T2.6: вложенность приезжает единственным признаком —
// `parent_call_id`; шаги субагента видны в live внутри строки его вызова.
describe("MessageList — вложенная лента субагента", () => {
  const subagentCall: SSEEvent[] = [
    { type: "tool_call_started", call_id: "sub-1", tool: "run_subagent" },
    {
      type: "tool_call_args",
      call_id: "sub-1",
      args: JSON.stringify({ agent_type: "judge", task: "Проверь выводы." }),
      truncated: false,
    },
  ];

  it("показывает шаги субагента строками внутри его вызова", () => {
    renderFeed(
      feedFrom([
        ...subagentCall,
        {
          type: "tool_call_started",
          call_id: "step-1",
          tool: "firecrawl_scrape",
          parent_call_id: "sub-1",
        },
        {
          type: "tool_call_args",
          call_id: "step-1",
          args: JSON.stringify({ url: "docs.langchain.com/subagents" }),
          truncated: false,
          parent_call_id: "sub-1",
        },
      ]),
    );

    // Идущий субагент развёрнут сам — шаги видны без клика.
    expect(screen.getByText(/Проверяющий субагент/)).toBeInTheDocument();
    expect(screen.getByText("Проверь выводы.")).toBeInTheDocument();
    expect(screen.getByText(/Читаю страницу/)).toBeInTheDocument();
  });

  it("не рисует синтетической первой строки вложенной ленты", () => {
    renderFeed(feedFrom(subagentCall));

    expect(screen.queryByText(/Получил задание/)).not.toBeInTheDocument();
  });

  it("закрывает строку субагента вердиктом", () => {
    renderFeed(
      feedFrom([
        ...subagentCall,
        {
          type: "tool_result",
          call_id: "sub-1",
          tool: "run_subagent",
          status: "success",
          content: "Три замечания по формулировкам.",
          truncated: false,
        },
      ]),
    );

    expect(screen.getByText("успешно")).toBeInTheDocument();
    // Завершённый субагент сворачивается — вердикт открывается по клику.
    expect(
      screen.queryByText("Три замечания по формулировкам."),
    ).not.toBeInTheDocument();
  });
});

// Требование итерации, ради которого лента вообще сделана одной структурой:
// ход, увиденный живым, и он же, загруженный из `parts` после перезагрузки,
// показывают одни и те же строки. Расхождение здесь означает, что F5 меняет
// картину работы агента у пользователя на глазах.
describe("живая лента совпадает с историей", () => {
  const events: SSEEvent[] = [
    { type: "reasoning_chunk", content: "Надо " },
    { type: "reasoning_chunk", content: "поискать" },
    { type: "tool_call_started", call_id: "c1", tool: "firecrawl_search" },
    {
      type: "tool_call_args",
      call_id: "c1",
      args: JSON.stringify({ query: "изоляция контекста" }),
      truncated: false,
    },
    {
      type: "tool_result",
      call_id: "c1",
      tool: "firecrawl_search",
      status: "success",
      content: "нашлось",
      truncated: false,
    },
    { type: "tool_call_started", call_id: "c2", tool: "update_section" },
    {
      type: "tool_call_args",
      call_id: "c2",
      args: JSON.stringify({ section_id: "Субагенты" }),
      truncated: false,
    },
    {
      type: "tool_result",
      call_id: "c2",
      tool: "update_section",
      status: "error",
      content: "раздела нет",
      truncated: false,
    },
    { type: "text_chunk", content: "Вот что нашлось." },
  ];

  const parts: MessagePart[] = [
    { type: "reasoning", content: "Надо поискать" },
    {
      type: "tool_call",
      call_id: "c1",
      tool: "firecrawl_search",
      args: JSON.stringify({ query: "изоляция контекста" }),
      args_truncated: false,
      status: "success",
      result_preview: "нашлось",
      result_truncated: false,
    },
    {
      type: "tool_call",
      call_id: "c2",
      tool: "update_section",
      args: JSON.stringify({ section_id: "Субагенты" }),
      args_truncated: false,
      status: "error",
      result_preview: "раздела нет",
      result_truncated: false,
    },
    { type: "text", content: "Вот что нашлось." },
  ];

  const historyMessage: Message = {
    id: "m1",
    role: "assistant",
    content: "Вот что нашлось.",
    created_at: null,
    artifacts: [],
    parts,
  };

  /**
   * Подписи строк ленты в порядке показа. Длительность выполнения вычищается:
   * её знает только live — в истории временны́х меток нет вовсе
   * (streaming.md § История: typed parts).
   */
  function rowLabels(container: HTMLElement): string[] {
    return within(container)
      .getAllByRole("button")
      .map((row) =>
        (row.textContent ?? "")
          .replace(/\d+(?:[.,]\d+)?\s*с/g, "")
          .replace(/\d+:\d{2}/g, "")
          .trim(),
      );
  }

  it("даёт те же строки на событиях потока и на parts истории", () => {
    const live = renderWithProviders(listTree(feedFrom(events)));
    const history = renderWithProviders(
      <MemoryRouter>
        <MessageItem message={historyMessage} projectId="p1" chatId="c1" />
      </MemoryRouter>,
    );

    expect(rowLabels(live.container)).toEqual(rowLabels(history.container));
    // Набор не пуст и содержит ровно те строки, ради которых ход показан.
    expect(rowLabels(live.container)).toEqual([
      "Рассуждения",
      "Ищу в интернете · «изоляция контекста»успешно",
      "Обновляю память проекта · раздел «Субагенты»ошибка",
    ]);
  });

  it("показывает текст ответа обоими путями", () => {
    const live = renderWithProviders(listTree(feedFrom(events)));
    const history = renderWithProviders(
      <MemoryRouter>
        <MessageItem message={historyMessage} projectId="p1" chatId="c1" />
      </MemoryRouter>,
    );

    // Текст сравнивается по содержимому контейнера, а не запросом по узлу:
    // живой markdown-рендер разбивает ответ на слова ради анимации появления,
    // и это единственное, чем два пути отличаются на экране.
    expect(live.container.textContent).toContain("Вот что нашлось.");
    expect(history.container.textContent).toContain("Вот что нашлось.");
  });
});

describe("MessageList — автопрокрутка за ростом ленты", () => {
  function scrollCount(): number {
    return vi.mocked(Element.prototype.scrollIntoView).mock.calls.length;
  }

  it("догоняет новую строку действия", () => {
    const first = feedFrom([
      { type: "tool_call_started", call_id: "c1", tool: "firecrawl_search" },
    ]);
    const { rerender } = renderFeed(first);
    const before = scrollCount();

    rerender(
      listTree(
        feedFrom([
          {
            type: "tool_call_started",
            call_id: "c1",
            tool: "firecrawl_search",
          },
          { type: "tool_call_started", call_id: "c2", tool: "update_section" },
        ]),
      ),
    );

    // Ход из одних tool-событий, без единого `text_chunk`, тоже обязан
    // держаться нижней границы: сигналом прокрутки был снятый `streamingText`.
    expect(scrollCount()).toBeGreaterThan(before);
  });

  it("догоняет растущий текст ответа, не меняющий числа строк", () => {
    const { rerender } = renderFeed(
      feedFrom([{ type: "text_chunk", content: "Начало" }]),
    );
    const before = scrollCount();

    rerender(
      listTree(
        feedFrom([
          { type: "text_chunk", content: "Начало" },
          { type: "text_chunk", content: " и продолжение ответа" },
        ]),
      ),
    );

    // Текст копится внутри одного элемента — одной длины массива тут мало.
    expect(scrollCount()).toBeGreaterThan(before);
  });

  it("догоняет терминальное уведомление, появившееся под лентой", () => {
    const feed = feedFrom([{ type: "text_chunk", content: "Начало" }]);
    const { rerender } = renderFeed(feed);
    const before = scrollCount();

    rerender(listTree(feed, { isStreaming: false, endNotice: "cancelled" }));

    expect(scrollCount()).toBeGreaterThan(before);
  });

  it("догоняет шаг, дорисованный во вложенную ленту субагента", () => {
    const subagent: SSEEvent[] = [
      { type: "tool_call_started", call_id: "sub-1", tool: "run_subagent" },
      {
        type: "tool_call_args",
        call_id: "sub-1",
        args: JSON.stringify({ agent_type: "judge", task: "Проверь выводы." }),
        truncated: false,
      },
    ];
    const { rerender } = renderFeed(feedFrom(subagent));
    const before = scrollCount();

    rerender(
      listTree(
        feedFrom([
          ...subagent,
          {
            type: "tool_call_started",
            call_id: "sub-1-step",
            tool: "firecrawl_search",
            parent_call_id: "sub-1",
          },
        ]),
      ),
    );

    // Шаг субагента приезжает в `children` строки его вызова: корневой массив
    // при этом не меняется, а лента на экране растёт — сигнал прокрутки обязан
    // считаться по всей ленте, включая вложенную.
    expect(scrollCount()).toBeGreaterThan(before);
  });
});

describe("MessageList — терминальные состояния", () => {
  it("сообщает об остановке генерации нейтральной строкой, без ошибки", () => {
    renderFeed([], { isStreaming: false, endNotice: "cancelled" });

    expect(screen.getByText("Генерация остановлена")).toBeInTheDocument();
  });

  it("ставит generic-карточку блокировки без деталей срабатывания", () => {
    renderFeed([], { isStreaming: false, endNotice: "blocked" });

    expect(
      screen.getByText("Ход остановлен системой безопасности"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Генерация остановлена")).not.toBeInTheDocument();
  });

  it("не показывает терминальное уведомление, пока ход идёт", () => {
    renderFeed([], { isStreaming: true, endNotice: "cancelled" });

    expect(screen.queryByText("Генерация остановлена")).not.toBeInTheDocument();
  });
});
