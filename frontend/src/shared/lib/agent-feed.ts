import type { MessagePart } from "@/shared/api/chats";
import type { SSEEvent } from "@/shared/api/sse";

/**
 * Модель ленты активности агента: одна структура, в которую одинаково
 * укладываются поток событий SSE v2 (live) и typed parts истории.
 *
 * Требование «live = история» техническое, а не косметическое: один и тот же
 * ход, поданный последовательностью событий и соответствующим ему списком
 * parts, обязан дать эквивалентную ленту — иначе перезагрузка страницы меняет
 * то, что пользователь уже видел. Поэтому нормализация живёт здесь, а не в
 * диспетчере стрима и не в компонентах.
 *
 * Модуль чистый: ни `Date.now()` по умолчанию (момент времени передаётся
 * аргументом), ни обращений к стору. Стор (`stores/stream-store.ts`) держит
 * это состояние и вызывает редьюсер.
 */

/**
 * Клиентский статус строки. `running` — вызов идёт прямо сейчас (только live);
 * `pending` — вызов без парного результата, ход оборвался (приезжает из
 * истории, streaming.md § История: typed parts).
 */
export type FeedItemStatus =
  | "running"
  | "success"
  | "error"
  | "pending"
  | "cancelled";

export interface ReasoningFeedItem {
  id: string;
  type: "reasoning";
  content: string;
}

export interface TextFeedItem {
  id: string;
  type: "text";
  content: string;
}

export interface ToolCallFeedItem {
  /** Совпадает с `callId`: `call_id` уникален в пределах хода. */
  id: string;
  type: "tool_call";
  callId: string;
  /** Сырое имя инструмента — подпись собирает `shared/config/agent-tools`. */
  tool: string;
  /** JSON-строка аргументов; при `argsTruncated` она обрезана и невалидна. */
  args: string | null;
  argsTruncated: boolean;
  status: FeedItemStatus;
  result: string | null;
  resultTruncated: boolean;
  /** Момент старта вызова; в истории неизвестен. */
  startedAt: number | null;
  /** Длительность исполнения — мета справа у завершённой строки. */
  durationMs: number | null;
  /** Вложенная лента: шаги субагента (события с `parent_call_id`). */
  children: AgentFeedItem[];
}

export interface AgentEventFeedItem {
  id: string;
  type: "agent_event";
  kind: string;
  payload: Record<string, unknown>;
}

export type AgentFeedItem =
  | ReasoningFeedItem
  | TextFeedItem
  | ToolCallFeedItem
  | AgentEventFeedItem;

export interface AgentFeedState {
  /** Элементы ленты в порядке прихода событий / порядке parts. */
  feed: AgentFeedItem[];
  /**
   * Ход отредактирован по security-блокировке: лента заменена заглушкой и
   * дальше не мутирует — события, пришедшие после терминального, её не
   * дописывают.
   */
  redacted: boolean;
}

/**
 * Единственный `kind` доменного `agent_event`, порождающий строку ленты:
 * у компакции нет собственного tool-вызова. `sphere_write` / `memory_write` /
 * `skill_context_write` всегда сопровождаются собственными `tool_call_*` того
 * же инструмента, и подпись из реестра по аргументам информативнее — строку
 * они не дублируют.
 */
const COMPACTION_KIND = "compaction";

function itemId(type: string, siblings: AgentFeedItem[]): string {
  return `${type}-${siblings.length}`;
}

/** Строка вызова по `call_id` — в корне ленты или в любой вложенной. */
export function findFeedCall(
  feed: AgentFeedItem[],
  callId: string,
): ToolCallFeedItem | null {
  for (const item of feed) {
    if (item.type !== "tool_call") continue;
    if (item.callId === callId) return item;
    const nested = findFeedCall(item.children, callId);
    if (nested) return nested;
  }
  return null;
}

/**
 * Точечное обновление строки вызова. `null` — вызова с таким `call_id` в ленте
 * нет; решение, что делать дальше, принимает вызывающая ветка редьюсера.
 */
function updateCall(
  feed: AgentFeedItem[],
  callId: string,
  update: (item: ToolCallFeedItem) => ToolCallFeedItem,
): AgentFeedItem[] | null {
  let changed = false;
  const next = feed.map((item) => {
    if (item.type !== "tool_call") return item;
    if (item.callId === callId) {
      changed = true;
      return update(item);
    }
    const children = updateCall(item.children, callId, update);
    if (children === null) return item;
    changed = true;
    return { ...item, children };
  });
  return changed ? next : null;
}

/**
 * Добавление элемента: с `parentCallId` — во вложенную ленту родителя. Если
 * родитель не анонсирован (события пришли не в том порядке или строка вызова
 * уже вне ленты), элемент не теряется — остаётся в корне.
 */
function appendAt(
  feed: AgentFeedItem[],
  parentCallId: string | undefined,
  make: (siblings: AgentFeedItem[]) => AgentFeedItem,
): AgentFeedItem[] {
  if (parentCallId !== undefined) {
    const nested = updateCall(feed, parentCallId, (parent) => ({
      ...parent,
      children: [...parent.children, make(parent.children)],
    }));
    if (nested !== null) return nested;
  }
  return [...feed, make(feed)];
}

/** Чанк дописывает текущий элемент того же типа либо открывает новый. */
function appendChunk(
  feed: AgentFeedItem[],
  type: "reasoning" | "text",
  chunk: string,
): AgentFeedItem[] {
  const last = feed.at(-1);
  if (last !== undefined && last.type === type) {
    const merged: ReasoningFeedItem | TextFeedItem = {
      ...last,
      content: last.content + chunk,
    };
    return [...feed.slice(0, -1), merged];
  }
  return [...feed, { id: itemId(type, feed), type, content: chunk }];
}

function elapsed(item: ToolCallFeedItem, now: number): number | null {
  return item.startedAt === null ? null : Math.max(0, now - item.startedAt);
}

function startedCall(
  callId: string,
  tool: string,
  now: number,
): ToolCallFeedItem {
  return {
    id: callId,
    type: "tool_call",
    callId,
    tool,
    args: null,
    argsTruncated: false,
    status: "running",
    result: null,
    resultTruncated: false,
    startedAt: now,
    durationMs: null,
    children: [],
  };
}

function withFeed(
  state: AgentFeedState,
  feed: AgentFeedItem[],
): AgentFeedState {
  return { feed, redacted: state.redacted };
}

/**
 * Редьюсер контракта SSE v2 в ленту. Возвращает исходное состояние без
 * изменений, если событие ленты не касается, — вызывающий стор на этом
 * не перерисовывает подписчиков.
 *
 * `now` передаётся аргументом, а не берётся из `Date.now()` внутри: длительность
 * вызова — часть модели, и она обязана быть проверяемой.
 */
export function applyStreamEvent(
  state: AgentFeedState,
  event: SSEEvent,
  now: number = Date.now(),
): AgentFeedState {
  if (state.redacted) return state;

  switch (event.type) {
    case "reasoning_chunk":
      return withFeed(
        state,
        appendChunk(state.feed, "reasoning", event.content),
      );

    case "text_chunk":
      return withFeed(state, appendChunk(state.feed, "text", event.content));

    case "tool_call_started": {
      // Повторный анонс того же вызова строку не задваивает.
      if (findFeedCall(state.feed, event.call_id) !== null) return state;
      return withFeed(
        state,
        appendAt(state.feed, event.parent_call_id, () =>
          startedCall(event.call_id, event.tool, now),
        ),
      );
    }

    case "tool_call_args": {
      const feed = updateCall(state.feed, event.call_id, (item) => ({
        ...item,
        args: event.args,
        argsTruncated: event.truncated,
      }));
      return feed === null ? state : withFeed(state, feed);
    }

    case "tool_result": {
      const close = (item: ToolCallFeedItem): ToolCallFeedItem => ({
        ...item,
        tool: item.tool || event.tool,
        status: event.status,
        result: event.content,
        resultTruncated: event.truncated,
        durationMs: elapsed(item, now),
      });
      const feed = updateCall(state.feed, event.call_id, close);
      if (feed !== null) return withFeed(state, feed);
      // Результат без анонса: строку всё равно показываем — имя инструмента
      // приезжает вместе с результатом.
      return withFeed(
        state,
        appendAt(state.feed, event.parent_call_id, () =>
          close(startedCall(event.call_id, event.tool, now)),
        ),
      );
    }

    case "tool_call_cancelled": {
      const feed = updateCall(state.feed, event.call_id, (item) => ({
        ...item,
        status: "cancelled",
        durationMs: elapsed(item, now),
      }));
      return feed === null ? state : withFeed(state, feed);
    }

    case "agent_event": {
      // Неизвестный kind модель не роняет — он просто не даёт строки.
      if (event.kind !== COMPACTION_KIND) return state;
      return withFeed(
        state,
        appendAt(state.feed, event.parent_call_id, (siblings) => ({
          id: itemId("agent_event", siblings),
          type: "agent_event",
          kind: event.kind,
          payload: event.payload,
        })),
      );
    }

    default:
      return state;
  }
}

/**
 * Редакция хода по `security_block`: вся лента заменяется единственным
 * текстовым элементом-заглушкой — симметрично тому, что отдаёт история
 * (streaming.md § История: typed parts — redacted-сообщение отдаёт один
 * `text`-part, без `reasoning`). Ни строки рассуждений, ни строк вызовов
 * заблокированного хода на экране не остаётся, и после перезагрузки
 * пользователь видит ровно то же самое.
 *
 * Прежнего состояния операция не читает — заглушка вытесняет ленту целиком,
 * поэтому аргумента состояния у неё нет.
 */
export function redactFeed(stubText: string): AgentFeedState {
  return {
    feed: [{ id: itemId("text", []), type: "text", content: stubText }],
    redacted: true,
  };
}

/**
 * Адаптер истории в ту же ленту. `status: "pending"` переносится как есть —
 * это «вызов не завершён», а не ошибка и не неизвестный статус.
 */
export function fromMessageParts(
  parts: MessagePart[] | undefined,
): AgentFeedItem[] {
  const feed: AgentFeedItem[] = [];
  for (const part of parts ?? []) {
    switch (part.type) {
      case "reasoning":
        feed.push({
          id: itemId("reasoning", feed),
          type: "reasoning",
          content: part.content,
        });
        break;
      case "text":
        feed.push({
          id: itemId("text", feed),
          type: "text",
          content: part.content,
        });
        break;
      case "tool_call":
        feed.push({
          id: part.call_id,
          type: "tool_call",
          callId: part.call_id,
          tool: part.tool,
          args: part.args,
          argsTruncated: part.args_truncated,
          status: part.status,
          result: part.result_preview,
          resultTruncated: part.result_truncated,
          startedAt: null,
          durationMs: null,
          children: [],
        });
        break;
    }
  }
  return feed;
}

/**
 * Блоки ленты: подряд идущие строки-действия рендерятся одной лентой на общей
 * соединительной нити, текст ассистента — отдельным блоком прозы
 * (`.feed` и `.part-text` мокапа).
 */
export type AgentFeedBlock =
  | { type: "feed"; items: AgentFeedItem[] }
  | { type: "text"; item: TextFeedItem };

export function groupFeedBlocks(feed: AgentFeedItem[]): AgentFeedBlock[] {
  const blocks: AgentFeedBlock[] = [];
  for (const item of feed) {
    if (item.type === "text") {
      blocks.push({ type: "text", item });
      continue;
    }
    const last = blocks.at(-1);
    if (last !== undefined && last.type === "feed") {
      last.items.push(item);
      continue;
    }
    blocks.push({ type: "feed", items: [item] });
  }
  return blocks;
}
