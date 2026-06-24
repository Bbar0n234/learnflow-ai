// Zustand auto-mock (activated by `vi.mock("zustand")` in src/test/setup.ts).
// Wraps the real create/createStore to record each store's reset function, then
// resets every store after each test — module-level stores otherwise leak state
// between tests. Adapted from the official Zustand testing guide for globals-off.
import { act } from "@testing-library/react";
import type * as ZustandExportedTypes from "zustand";
import { afterEach } from "vitest";

export * from "zustand";

import {
  create as actualCreate,
  createStore as actualCreateStore,
} from "zustand";

export const storeResetFns = new Set<() => void>();

const createUncurried = <T>(
  stateCreator: ZustandExportedTypes.StateCreator<T>,
) => {
  const store = actualCreate(stateCreator);
  const initialState = store.getInitialState();
  storeResetFns.add(() => {
    store.setState(initialState, true);
  });
  return store;
};

export const create = (<T>(
  stateCreator?: ZustandExportedTypes.StateCreator<T>,
) => {
  return typeof stateCreator === "function"
    ? createUncurried(stateCreator)
    : createUncurried;
}) as typeof ZustandExportedTypes.create;

const createStoreUncurried = <T>(
  stateCreator: ZustandExportedTypes.StateCreator<T>,
) => {
  const store = actualCreateStore(stateCreator);
  const initialState = store.getInitialState();
  storeResetFns.add(() => {
    store.setState(initialState, true);
  });
  return store;
};

export const createStore = (<T>(
  stateCreator?: ZustandExportedTypes.StateCreator<T>,
) => {
  return typeof stateCreator === "function"
    ? createStoreUncurried(stateCreator)
    : createStoreUncurried;
}) as typeof ZustandExportedTypes.createStore;

afterEach(() => {
  act(() => {
    storeResetFns.forEach((resetFn) => {
      resetFn();
    });
  });
});
