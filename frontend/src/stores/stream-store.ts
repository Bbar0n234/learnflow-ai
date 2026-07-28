import { create } from "zustand";

import type { SSEEvent } from "@/shared/api/sse";
import {
  applyStreamEvent,
  redactFeed,
  type AgentFeedState,
} from "@/shared/lib/agent-feed";

export interface StreamingArtifact {
  id: string;
  title: string;
  type: string;
}

/**
 * Эфемерное состояние активного стрима. Лента активности живёт моделью
 * `shared/lib/agent-feed` (`feed` + `redacted` приходят из неё) — плоского
 * `activeTool` больше нет: параллельные вызовы адресуются по `call_id` и
 * закрываются независимо друг от друга.
 *
 * Стор — не source of truth: после `done` данные рефетчатся с сервера, и ту же
 * ленту рисует история.
 */
interface StreamState extends AgentFeedState {
  isStreaming: boolean;
  streamingChatId: string | null;
  streamingArtifacts: StreamingArtifact[];
  isReviewing: boolean;
  startStream: (chatId: string) => void;
  /** Единственная точка мутации ленты: событие уходит в редьюсер модели. */
  applyEvent: (event: SSEEvent) => void;
  addArtifact: (artifact: StreamingArtifact) => void;
  redact: (stubText: string) => void;
  setReviewing: (value: boolean) => void;
  endStream: () => void;
}

type StreamData = Omit<
  StreamState,
  | "startStream"
  | "applyEvent"
  | "addArtifact"
  | "redact"
  | "setReviewing"
  | "endStream"
>;

/** Пустое состояние — фабрика, а не константа: массивы не разделяются сбросами. */
function idleState(): StreamData {
  return {
    isStreaming: false,
    streamingChatId: null,
    streamingArtifacts: [],
    feed: [],
    redacted: false,
    isReviewing: false,
  };
}

export const useStreamStore = create<StreamState>()((set) => ({
  ...idleState(),
  // Старт нового стрима сбрасывает остатки предыдущего целиком — иначе лента
  // прошлого хода дописывалась бы событиями нового.
  startStream: (chatId) =>
    set({ ...idleState(), isStreaming: true, streamingChatId: chatId }),
  applyEvent: (event) => set((s) => applyStreamEvent(s, event)),
  addArtifact: (artifact) =>
    set((s) => ({ streamingArtifacts: [...s.streamingArtifacts, artifact] })),
  // Редакция гасит и ревью: индикатор проверки ответа не должен пережить
  // блокировку хода.
  redact: (stubText) => set({ ...redactFeed(stubText), isReviewing: false }),
  setReviewing: (value) => set({ isReviewing: value }),
  endStream: () => set(idleState()),
}));
