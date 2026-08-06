import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Unit on the build-time SIEM flag. `SIEM_ENABLED` is a module-level constant
// evaluated once, when the module is first imported, so each case stubs
// `import.meta.env` and re-imports the module through a reset registry —
// exactly the shape the real bundle has, where Vite inlines the value at build
// time and nothing can change it afterwards.
//
// The rule under test is `(VITE_SIEM_ENABLED ?? "true") !== "false"`: opt-out,
// not opt-in. Every build path that does not pass the build-arg (`make dev-fe`,
// a bare `npm run build`, `vite dev`) has to keep the Security UI reachable —
// only the literal lowercase string "false" takes it away.
//
// That literal matters, because nothing on the way normalizes it. Compose does
// a raw passthrough (`VITE_SIEM_ENABLED: ${SIEM_ENABLED:-true}`), so whatever
// the operator typed into the production .env arrives here verbatim: with
// `SIEM_ENABLED=0` the backend stops emitting (pydantic reads it as false) and
// this flag stays on. The asymmetry is pinned from the other side in
// `backend/tests/siem_toggle/test_settings_contract.py`.

async function loadFlag(): Promise<boolean> {
  vi.resetModules();
  const module = await import("./feature-flags");
  return module.SIEM_ENABLED;
}

beforeEach(() => {
  vi.unstubAllEnvs();
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe("SIEM_ENABLED", () => {
  it("is on when the variable is not defined at all", async () => {
    vi.stubEnv("VITE_SIEM_ENABLED", undefined);

    await expect(loadFlag()).resolves.toBe(true);
  });

  it('is off for the literal "false" that the docker build passes', async () => {
    vi.stubEnv("VITE_SIEM_ENABLED", "false");

    await expect(loadFlag()).resolves.toBe(false);
  });

  // Anything that is not literally "false" leaves the UI on. Listed value by
  // value because this is the half an operator can get wrong: `SIEM_ENABLED=0`
  // or `=False` in the production .env reaches this flag unchanged and does
  // *not* hide the Security page, even though the backend already stopped
  // emitting. The supported way to turn the subsystem off is the lowercase
  // literal `SIEM_ENABLED=false` (production.md § SIEM, шаг 1).
  it.each(["true", "1", "0", "no", "False", "FALSE", ""])(
    'stays on for %o, since only the exact string "false" disables it',
    async (value) => {
      vi.stubEnv("VITE_SIEM_ENABLED", value);

      await expect(loadFlag()).resolves.toBe(true);
    },
  );
});
