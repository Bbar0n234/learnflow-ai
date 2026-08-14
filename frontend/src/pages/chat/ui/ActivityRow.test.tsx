import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { FeedItemStatus, ToolCallFeedItem } from "@/shared/lib/agent-feed";

import { ActivityRow } from "./ActivityRow";

// Integration (компонент строки ленты): статусная мета завершённого вызова.
// Трек T1 покрасил галочку успеха новым токеном `--success` — здесь страхуем
// два факта: статус по-прежнему читается текстом (доступность не свелась к
// цвету) и к иконке применена нужная токен-утилита. Крестик ошибки — регресс:
// он остаётся деструктивным и вместе с галочкой перекраситься не должен.
//
// Утилита-класс здесь и есть наблюдаемый контракт: реальный цвет считает
// браузер по `index.css`, jsdom его не исполняет — зелёная галочка в обеих
// темах проверяется вручную, кейс {T1.1}.

function toolCall(status: FeedItemStatus): ToolCallFeedItem {
  return {
    id: "call-1",
    type: "tool_call",
    callId: "call-1",
    tool: "read_url",
    args: '{"url":"https://example.com"}',
    argsTruncated: false,
    status,
    result: "ok",
    resultTruncated: false,
    startedAt: null,
    durationMs: 1200,
    children: [],
  };
}

describe("ActivityRow — статусная мета", () => {
  it("объявляет успех текстом и красит галочку токеном успеха", () => {
    const { container } = render(<ActivityRow item={toolCall("success")} />);

    expect(screen.getByText("успешно")).toBeInTheDocument();
    // Ищем саму иконку, а не соседа подписи: порядок узлов внутри `StatusMeta`
    // и обёртки вокруг иконки — вёрстка, а не контракт, и менять их можно без
    // изменения поведения.
    expect(container.querySelector(".lucide-check")).toHaveClass(
      "text-success",
    );
  });

  it("объявляет ошибку текстом и оставляет крестик деструктивным", () => {
    const { container } = render(<ActivityRow item={toolCall("error")} />);

    expect(screen.getByText("ошибка")).toBeInTheDocument();
    expect(container.querySelector(".lucide-x")).toHaveClass(
      "text-destructive",
    );
  });
});
