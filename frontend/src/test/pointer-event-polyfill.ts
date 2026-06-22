// Local test helper (not part of the frozen harness). jsdom does not implement
// the `PointerEvent` constructor, but Base UI components (Switch, Select) call
// `new PointerEvent(...)` in their click handlers. Importing this module installs
// a minimal MouseEvent-backed polyfill so those interactions run under jsdom.
// Import it from any test that drives a Base UI Switch/Select via user-event.

interface PointerEventInitLike extends MouseEventInit {
  pointerId?: number;
  pointerType?: string;
  isPrimary?: boolean;
}

if (typeof globalThis.PointerEvent === "undefined") {
  class PointerEventPolyfill extends MouseEvent {
    pointerId: number;
    pointerType: string;
    isPrimary: boolean;

    constructor(type: string, params: PointerEventInitLike = {}) {
      super(type, params);
      this.pointerId = params.pointerId ?? 0;
      this.pointerType = params.pointerType ?? "";
      this.isPrimary = params.isPrimary ?? false;
    }
  }

  globalThis.PointerEvent =
    PointerEventPolyfill as unknown as typeof PointerEvent;
}

export {};
