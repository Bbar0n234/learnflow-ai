import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TypedTitle } from "./TypedTitle";

// Unit (feat-002, T2.4): the auto-title typing animation. The component is a
// presentational layer over the cached title — it animates exactly one
// transition, «Новый чат» → generated name (design-brief § Доставка title на
// фронт, mockup `applyTitle(..., flash=true)`), and shows every other value
// change instantly. jsdom has no `matchMedia`, so the reduced-motion media
// query is stubbed per test (in a browser it is always available).

const PLACEHOLDER = "Новый чат";
const GENERATED = "Интегралы";
// Mockup timing: ~38 ms per character (mockups/chat-ux.html `typeInto`).
const TYPE_INTERVAL_MS = 38;
// The highlight is held this long after the last character, then fades out.
const HIGHLIGHT_HOLD_MS = 700;
// What a real host passes down (`ChatHeader.tsx`, `ChatList.tsx`): its own
// colour utility among the rest.
const HOST_CLASSNAME =
  "truncate font-serif text-[17px] font-semibold tracking-tight text-foreground";

const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

// The stub answers only the reduced-motion feature: a component asking for some
// other media query must not be told "yes" by accident.
function stubReducedMotion(matches: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query === REDUCED_MOTION_QUERY && matches,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  }));
}

beforeEach(() => {
  stubReducedMotion(false);
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

/** Advance the typing timer by `chars` character ticks. */
function typeChars(chars: number) {
  act(() => {
    vi.advanceTimersByTime(TYPE_INTERVAL_MS * chars);
  });
}

describe("TypedTitle", () => {
  it("shows the current title as-is on first render", () => {
    const { container } = render(
      <TypedTitle text={GENERATED} animateFrom={PLACEHOLDER} />,
    );

    expect(container.textContent).toBe(GENERATED);
  });

  it("types the generated title character by character over the placeholder", () => {
    const { container, rerender } = render(
      <TypedTitle text={PLACEHOLDER} animateFrom={PLACEHOLDER} />,
    );

    rerender(<TypedTitle text={GENERATED} animateFrom={PLACEHOLDER} />);

    // The placeholder is wiped and the name arrives one character at a time.
    expect(container.textContent).toBe("");
    typeChars(3);
    expect(container.textContent).toBe(GENERATED.slice(0, 3));
    typeChars(GENERATED.length);
    expect(container.textContent).toBe(GENERATED);
  });

  // Regression of `{T2.1}`: the typing highlight was lost in two hosts out of
  // three. Classes are merged with `twMerge`, which keeps the last utility of a
  // conflicting group, and the host's `className` carries its own text colour
  // (`text-foreground` in the chat header and in the project chat list) — put
  // before it, `text-primary` was dropped before ever reaching the DOM and the
  // typing ran in the ordinary colour. Asserted on classes rather than on the
  // computed colour: with `css: false` jsdom turns Tailwind utilities into
  // nothing.
  it("keeps the typing highlight when the host sets its own text colour", () => {
    const { container, rerender } = render(
      <TypedTitle
        text={PLACEHOLDER}
        animateFrom={PLACEHOLDER}
        className={HOST_CLASSNAME}
      />,
    );

    rerender(
      <TypedTitle
        text={GENERATED}
        animateFrom={PLACEHOLDER}
        className={HOST_CLASSNAME}
      />,
    );
    typeChars(2);

    // While typing, the highlight overrides the host's colour…
    const title = container.firstElementChild as HTMLElement;
    expect(title).toHaveClass("text-primary");
    expect(title).not.toHaveClass("text-foreground");
    // …and the host's other utilities are left alone.
    expect(title).toHaveClass("truncate", "text-[17px]");

    typeChars(GENERATED.length);
    act(() => {
      vi.advanceTimersByTime(HIGHLIGHT_HOLD_MS);
    });

    // Highlight released — the host's colour is back.
    expect(container.textContent).toBe(GENERATED);
    expect(title).not.toHaveClass("text-primary");
    expect(title).toHaveClass("text-foreground");
  });

  it("replaces an already generated title instantly (rename does not type)", () => {
    const { container, rerender } = render(
      <TypedTitle text={GENERATED} animateFrom={PLACEHOLDER} />,
    );

    rerender(<TypedTitle text="Моё название" animateFrom={PLACEHOLDER} />);

    expect(container.textContent).toBe("Моё название");
  });

  it("shows the generated title at once when the user asked for reduced motion", () => {
    stubReducedMotion(true);
    const { container, rerender } = render(
      <TypedTitle text={PLACEHOLDER} animateFrom={PLACEHOLDER} />,
    );

    rerender(<TypedTitle text={GENERATED} animateFrom={PLACEHOLDER} />);

    expect(container.textContent).toBe(GENERATED);
  });

  it("renders with the requested tag so hosts keep their own semantics", () => {
    const { container } = render(
      <TypedTitle text={GENERATED} animateFrom={PLACEHOLDER} as="p" />,
    );

    expect(container.firstElementChild?.tagName).toBe("P");
  });

  it("leaves no running timers behind when unmounted mid-typing", () => {
    const { rerender, unmount } = render(
      <TypedTitle text={PLACEHOLDER} animateFrom={PLACEHOLDER} />,
    );
    rerender(<TypedTitle text={GENERATED} animateFrom={PLACEHOLDER} />);
    typeChars(2);
    // Typing is genuinely under way — otherwise "no timers left" would be
    // vacuously true.
    expect(vi.getTimerCount()).toBeGreaterThan(0);

    unmount();

    expect(vi.getTimerCount()).toBe(0);
  });

  it("leaves no running timers behind when unmounted right after typing ends", () => {
    const { container, rerender, unmount } = render(
      <TypedTitle text={PLACEHOLDER} animateFrom={PLACEHOLDER} />,
    );
    rerender(<TypedTitle text={GENERATED} animateFrom={PLACEHOLDER} />);
    typeChars(GENERATED.length);
    // The name is fully typed, but the highlight is still held — a second timer
    // waiting to fade it out.
    expect(container.textContent).toBe(GENERATED);
    expect(vi.getTimerCount()).toBeGreaterThan(0);

    unmount();

    expect(vi.getTimerCount()).toBe(0);
  });
});
