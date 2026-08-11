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
// same feed the history renders (`shared/lib/agent-feed`); карточек артефактов
// в живом ходе нет — создание видно строкой ленты, полная карточка приезжает
// из истории после завершения хода.

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

// Карточек-плейсхолдеров в живом ходе больше нет: стоя после живых блоков, они
// «плыли» вниз с каждым чанком текста. Генерация видна строкой ленты — той же,
// что и любой другой вызов.
describe("MessageList — генерация изображения в живом ходе", () => {
  it("показывает идущую генерацию строкой ленты, без карточки-плейсхолдера", () => {
    renderFeed(feedFrom(imageCall("call-1", "кот на подоконнике")));

    expect(screen.getByText(/Генерирую изображение/)).toBeInTheDocument();
    // Плейсхолдер жил ролью status; пока вызов идёт, легитимных status-строк
    // нет вовсе (пауза при идущем вызове не показывается) — любая всплывшая
    // карточка видна как лишний status.
    expect(screen.queryAllByRole("status")).toHaveLength(0);
  });

  it("закрывает строку генерации результатом вызова", () => {
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

    // Успешный вызов читается совершенным видом; сама карточка приедет из
    // истории после завершения хода.
    expect(screen.getByText(/Сгенерировал изображение/)).toBeInTheDocument();
    expect(screen.getByText("успешно")).toBeInTheDocument();
  });

  it("не рисует карточку артефакта в живом ходе даже после успеха вызова", () => {
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

    // Карточка артефакта — ссылка на его страницу; в живом ходе ссылок нет
    // вовсе (история пуста), полная карточка приедет из истории после
    // завершения хода. Стоя после живых блоков, она «плыла» бы вниз с каждым
    // чанком.
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
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
          tool: "search_web",
        },
        {
          type: "tool_result",
          call_id: "call-1",
          tool: "search_web",
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
        tool: "read_url",
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
            tool: "read_url",
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
          tool: "search_web",
        },
        {
          type: "tool_result",
          call_id: "call-1",
          tool: "search_web",
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

  // Регрессия финального интеграционного прогона (r2 на `aed0a10`): экран
  // простоял немым 27,75 с (+75,62…+103,37) — хвостом ленты был текст, в
  // который перестали дописывать (последний `text_chunk` +75,35, следующее
  // событие +103,32), а признак живости выводился из позиции: раз элемент
  // последний, значит поток пишет в него. На проводе в это окно уложились пять
  // `heartbeat`. Кейс отличает замолчавший хвост от отсутствия элементов:
  // лента непуста и её состав не меняется — паузу зажигает только время.
  it("возвращает строку-паузу, когда в хвостовой текст перестали дописывать", async () => {
    vi.useFakeTimers();
    try {
      renderFeed(
        feedFrom([{ type: "text_chunk", content: "Вот что нашлось" }]),
      );

      // Только что приехавший чанк — это живой хвост, паузе места нет.
      expect(
        screen.queryByRole("status", { name: "Агент думает" }),
      ).not.toBeInTheDocument();

      await act(async () => {
        vi.advanceTimersByTime(2500);
      });

      expect(
        screen.getByRole("status", { name: "Агент думает" }),
      ).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("не зажигает паузу, пока чанки продолжают приходить", async () => {
    vi.useFakeTimers();
    try {
      const { rerender } = renderFeed(
        feedFrom([{ type: "text_chunk", content: "Вот " }]),
      );

      // Порог сторожится с обеих сторон: до него паузы нет...
      await act(async () => {
        vi.advanceTimersByTime(1500);
      });
      expect(
        screen.queryByRole("status", { name: "Агент думает" }),
      ).not.toBeInTheDocument();

      // ...а пришедший чанк отсчёт начинает заново — иначе пауза мигала бы
      // посреди нормальной генерации, что хуже её отсутствия.
      rerender(
        listTree(
          feedFrom([
            { type: "text_chunk", content: "Вот " },
            { type: "text_chunk", content: "что нашлось" },
          ]),
        ),
      );
      await act(async () => {
        vi.advanceTimersByTime(1500);
      });

      expect(
        screen.queryByRole("status", { name: "Агент думает" }),
      ).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("снимает паузу тем же кадром, которым поток заговорил снова", async () => {
    vi.useFakeTimers();
    try {
      const { rerender } = renderFeed(
        feedFrom([{ type: "text_chunk", content: "Вот " }]),
      );
      await act(async () => {
        vi.advanceTimersByTime(2500);
      });
      expect(
        screen.getByRole("status", { name: "Агент думает" }),
      ).toBeInTheDocument();

      // Часы не двигаются: паузу снимает факт прихода данных, а не таймер.
      rerender(
        listTree(
          feedFrom([
            { type: "text_chunk", content: "Вот " },
            { type: "text_chunk", content: "что нашлось" },
          ]),
        ),
      );

      expect(
        screen.queryByRole("status", { name: "Агент думает" }),
      ).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("снимает подпись процесса с замолчавшего рассуждения, не пряча его текст", async () => {
    vi.useFakeTimers();
    try {
      renderFeed(
        feedFrom([{ type: "reasoning_chunk", content: "надо поискать" }]),
      );
      expect(screen.getByText("Рассуждаю")).toBeInTheDocument();

      await act(async () => {
        vi.advanceTimersByTime(2500);
      });

      // Подпись и пауза отвечают на один вопрос и обязаны отвечать одинаково:
      // строка «Рассуждаю» рядом со строкой-паузой была бы враньём.
      expect(screen.getByText("Рассуждал")).toBeInTheDocument();
      expect(screen.queryByText("Рассуждаю")).not.toBeInTheDocument();
      expect(
        screen.getByRole("status", { name: "Агент думает" }),
      ).toBeInTheDocument();
      // Уже показанный текст рассуждения на паузе не прячется.
      expect(screen.getByText("надо поискать")).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("подписывает хвостовое рассуждение процессом и держит его развёрнутым", () => {
    renderFeed(
      feedFrom([{ type: "reasoning_chunk", content: "надо поискать" }]),
    );

    expect(screen.getByText("Рассуждаю")).toBeInTheDocument();
    expect(screen.queryByText("Рассуждал")).not.toBeInTheDocument();
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
          tool: "search_web",
        },
      ]),
    );

    expect(screen.getByText("Рассуждал")).toBeInTheDocument();
    expect(screen.queryByText("Рассуждаю")).not.toBeInTheDocument();
  });

  it("показывает счётчик времени только у действия, идущего дольше порога", async () => {
    vi.useFakeTimers();
    try {
      const feed = feedFrom([
        {
          type: "tool_call_started",
          call_id: "call-1",
          tool: "search_web",
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
          tool: "read_url",
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
    { type: "tool_call_started", call_id: "c1", tool: "search_web" },
    {
      type: "tool_call_args",
      call_id: "c1",
      args: JSON.stringify({ query: "изоляция контекста" }),
      truncated: false,
    },
    {
      type: "tool_result",
      call_id: "c1",
      tool: "search_web",
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
      tool: "search_web",
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
      "Рассуждал",
      "Искал в интернете · «изоляция контекста»успешно",
      "Обновлял память проекта · раздел «Субагенты»ошибка",
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
      { type: "tool_call_started", call_id: "c1", tool: "search_web" },
    ]);
    const { rerender } = renderFeed(first);
    const before = scrollCount();

    rerender(
      listTree(
        feedFrom([
          {
            type: "tool_call_started",
            call_id: "c1",
            tool: "search_web",
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
            tool: "search_web",
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
