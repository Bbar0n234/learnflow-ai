import { create } from "zustand";

import type { SSEEvent } from "@/shared/api/sse";
import {
  applyStreamEvent,
  redactFeed,
  type AgentFeedState,
} from "@/shared/lib/agent-feed";

/**
 * Эфемерное состояние активного стрима. Лента активности живёт моделью
 * `shared/lib/agent-feed` (`feed` + `redacted` приходят из неё) — плоского
 * `activeTool` больше нет: параллельные вызовы адресуются по `call_id` и
 * закрываются независимо друг от друга.
 *
 * Стор — не source of truth: после `done` данные рефетчатся с сервера, и ту же
 * ленту рисует история.
 *
 * Владелец и owner-guard: `ChatThread` не перемонтируется при смене чата
 * (`chats/:cid` рендерит тот же компонент без `key`), поэтому поток чата A,
 * не абортящийся при переключении на B, продолжает писать события в стор уже
 * после `startStream(B)`. Действия, которыми управляет поток
 * (`applyEvent`/`redact`/`setReviewing`/`endStream`), принимают владельца
 * первым аргументом и сверяют его с `streamingChatId`: событие или терминал
 * потока, который стору больше не принадлежит, — no-op. Дисциплина
 * вызывающего («хук больше не пишет после чужого `startStream`») здесь не
 * масштабируется — писателей в будущем может стать больше одного, поэтому
 * инвариант держит сам стор, а не проверяющий его код снаружи.
 */
interface StreamState extends AgentFeedState {
  isStreaming: boolean;
  streamingChatId: string | null;
  isReviewing: boolean;
  startStream: (chatId: string) => void;
  /**
   * Единственная точка мутации ленты: событие уходит в редьюсер модели — и
   * только для владельца текущего стрима (`ownerChatId === streamingChatId`).
   */
  applyEvent: (ownerChatId: string, event: SSEEvent) => void;
  /** Владелец сверяется так же, как у остальных охраняемых действий. */
  redact: (ownerChatId: string, stubText: string) => void;
  /** Владелец сверяется так же, как у остальных охраняемых действий. */
  setReviewing: (ownerChatId: string, value: boolean) => void;
  /** Терминал потока: гасит стрим, только если поток всё ещё владеет стором. */
  endStream: (ownerChatId: string) => void;
  /**
   * Неохраняемый сброс для cleanup на unmount. Отдельно от `endStream`
   * намеренно: уход с экрана убивает эфемерное состояние безусловно — у этого
   * действия нет и не должно быть владельца, тогда как `endStream` — терминал
   * конкретного потока и обязан сверяться. Схлопывать эти два смысла в одно
   * действие нельзя: «мой поток закончился» и «экран ушёл, чистим всё» —
   * разная семантика, у которой разная защита.
   */
  reset: () => void;
}

type StreamData = Omit<
  StreamState,
  | "startStream"
  | "applyEvent"
  | "redact"
  | "setReviewing"
  | "endStream"
  | "reset"
>;

/** Пустое состояние — фабрика, а не константа: массивы не разделяются сбросами. */
function idleState(): StreamData {
  return {
    isStreaming: false,
    streamingChatId: null,
    feed: [],
    redacted: false,
    isReviewing: false,
  };
}

export const useStreamStore = create<StreamState>()((set) => ({
  ...idleState(),
  // Старт нового стрима сбрасывает остатки предыдущего целиком — иначе лента
  // прошлого хода дописывалась бы событиями нового. Владельца не сверяет:
  // именно он его и устанавливает.
  startStream: (chatId) =>
    set({ ...idleState(), isStreaming: true, streamingChatId: chatId }),
  // Owner-guard: возвращает тот же объект состояния `s`, а не пересобранный,
  // если владелец не совпадает со `streamingChatId` — zustand сверяет
  // результат апдейтера через `Object.is` и при совпадении ссылок не будит
  // подписчиков вовсе (тем же приёмом уже пользуется `applyStreamEvent` для
  // редактированной ленты).
  applyEvent: (ownerChatId, event) =>
    set((s) =>
      s.streamingChatId !== ownerChatId ? s : applyStreamEvent(s, event),
    ),
  // Редакция по `security_block` терминальна: ход на этом закончился, поэтому
  // она же закрывает стрим — но, в отличие от `endStream`, не стирает ленту, а
  // схлопывает её в заглушку и запирает флагом `redacted`. Гасить стрим здесь
  // обязательно: пока `isStreaming` держится, живой регион показывает заглушку
  // рядом с той же заглушкой, приехавшей из отрефетченной истории, а композер
  // остаётся с кнопкой отмены хода, которого уже нет. Из-за этого заглушку из
  // ленты пользователь и не читает — её показывает история; лента же остаётся
  // запертой на случай событий, пришедших после терминального.
  //
  // Ревью гасится по той же причине, что и стрим: от схлопнутого хода на
  // экране не должно остаться индикатора проверки ответа — иначе `redact`
  // оставляет живые остатки там, где `endStream` чистит всё.
  //
  // Узкий побочный эффект owner-guard'а: `redact` обнуляет `streamingChatId`
  // вместе с гашением стрима, поэтому терминал того же потока, пришедший
  // после `security_block` (например, дублирующее событие), тоже становится
  // no-op — гарда не отличает «поток сменился» от «поток уже погашен своим же
  // терминалом». Согласуется с комментарием выше про запертую ленту: событий
  // после терминального она не ждёт ни от кого, включая бывшего владельца.
  redact: (ownerChatId, stubText) =>
    set((s) =>
      s.streamingChatId !== ownerChatId
        ? s
        : {
            ...redactFeed(stubText),
            isStreaming: false,
            streamingChatId: null,
            isReviewing: false,
          },
    ),
  setReviewing: (ownerChatId, value) =>
    set((s) =>
      s.streamingChatId !== ownerChatId ? s : { isReviewing: value },
    ),
  endStream: (ownerChatId) =>
    set((s) => (s.streamingChatId !== ownerChatId ? s : idleState())),
  // Неохраняемый сброс: cleanup на unmount убивает эфемерное состояние
  // безусловно, независимо от того, чей поток был активен.
  reset: () => set(idleState()),
}));
