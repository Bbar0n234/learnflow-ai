import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Skeleton } from "./skeleton";

// Unit: плашка-плейсхолдер, из которой волна 2 собирает скелетоны списков.
// Проверяем ровно её контракт как строительного блока: размеры задаёт
// потребитель, а пульсацию плашка несёт сама (рецепты T1 поэтому не оборачивают
// группу в свой `animate-pulse`). Сам факт мерцания jsdom не исполняет — вид
// скелетонов против мокапа проверяется вручную, кейс {T1.9}.

describe("Skeleton", () => {
  it("несёт пульсацию сам, без обёртки-контейнера", () => {
    const { container } = render(<Skeleton />);

    expect(container.firstElementChild).toHaveClass("animate-pulse");
  });

  it("принимает размеры потребителя, не теряя базовую заливку", () => {
    const { container } = render(
      <Skeleton className="h-4 w-16 rounded-full" />,
    );

    const plate = container.firstElementChild;
    expect(plate).toHaveClass("h-4", "w-16", "rounded-full", "bg-muted");
  });
});
