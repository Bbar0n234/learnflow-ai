// События SSE-протокола агент-стрима. Спецификация — doc/tech/streaming.md.
//
// Payload'ы плоские: сервер шлёт `{"type": ..., ...payload}` без вложенного
// `data`. `trace_id` до клиента не доезжает — его перехватывает ChatService и
// отдаёт полем `done.trace_id`.

/** Статус завершившегося вызова инструмента на проводе (в истории есть ещё `pending`). */
export type ToolResultStatus = "success" | "error";

export type SSEEvent =
  | { type: "stream_started" }
  | { type: "heartbeat" }
  | { type: "reasoning_chunk"; content: string }
  | { type: "text_chunk"; content: string }
  | {
      type: "tool_call_started";
      call_id: string;
      tool: string;
      parent_call_id?: string;
    }
  | {
      type: "tool_call_args";
      call_id: string;
      args: string;
      truncated: boolean;
      parent_call_id?: string;
    }
  | { type: "tool_call_cancelled"; call_id: string }
  | {
      type: "tool_result";
      call_id: string;
      tool: string;
      status: ToolResultStatus;
      content: string;
      truncated: boolean;
      parent_call_id?: string;
    }
  | {
      type: "agent_event";
      // Доменные kind'ы — `sphere_write` | `memory_write` | `skill_context_write`
      // | `compaction`; список растёт без версионирования, поэтому тип открытый:
      // неизвестный kind обязан проходить мимо, а не ронять потребителя.
      kind: string;
      payload: Record<string, unknown>;
      parent_call_id?: string;
    }
  | {
      type: "artifact_created";
      path: string;
      title: string;
      artifact_type: string;
    }
  | {
      type: "artifact_updated";
      path: string;
      title: string;
      artifact_type: string;
      // Счётчики строк текстового обновления; `null` — бинарный файл или
      // превышение лимита размера (§ Эмиссия artifact_updated, design-brief).
      diff: { added: number; removed: number } | null;
    }
  | { type: "final_output_review_started" }
  | { type: "final_output_review_complete" }
  | { type: "title_updated"; title: string }
  // Payload всегда пуст: reason/checkpoint/detection_layer сервер наружу не отдаёт.
  | { type: "security_block" }
  | { type: "cancelled" }
  | { type: "error"; detail: string }
  | { type: "done"; message_id?: string; trace_id?: string };

export type SSEEventType = SSEEvent["type"];

/**
 * Фрейм как он приходит с провода — до сужения до `SSEEvent`.
 *
 * Контракт растёт без версионирования пути (streaming.md § Forward-compat):
 * неизвестный `type` обязан логироваться и игнорироваться, а не ронять
 * диспетчер. Поэтому распарсенный JSON типизируется этой формой, и только
 * `isKnownSSEEvent` сужает его до словаря, который фронт умеет обрабатывать.
 */
export interface SSEFrame {
  type: string;
  [key: string]: unknown;
}

const KNOWN_SSE_EVENT_TYPES: ReadonlySet<string> = new Set<SSEEventType>([
  "stream_started",
  "heartbeat",
  "reasoning_chunk",
  "text_chunk",
  "tool_call_started",
  "tool_call_args",
  "tool_call_cancelled",
  "tool_result",
  "agent_event",
  "artifact_created",
  "artifact_updated",
  "final_output_review_started",
  "final_output_review_complete",
  "title_updated",
  "security_block",
  "cancelled",
  "error",
  "done",
]);

export function isKnownSSEEvent(frame: SSEFrame): frame is SSEFrame & SSEEvent {
  return KNOWN_SSE_EVENT_TYPES.has(frame.type);
}
